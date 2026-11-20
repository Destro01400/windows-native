#pragma once

#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif

#include <windows.h>
#include <unknwn.h>
#include <dwmapi.h>
#include <d3d11_1.h>
#include <dxgi1_3.h>
#include <d2d1_2.h>
#include <d2d1_1helper.h>
#include <dwrite.h>
#include <dcomp.h>
#include <wrl/client.h>

#include <algorithm>
#include <string>
#include <string_view>

namespace {{APP_NAME}}_native
{
using Microsoft::WRL::ComPtr;

class D2DWindow final
{
public:
    D2DWindow() = default;
    ~D2DWindow() = default;

    D2DWindow(const D2DWindow&) = delete;
    D2DWindow& operator=(const D2DWindow&) = delete;

    bool Create(HINSTANCE instance, std::wstring_view title, UINT logicalWidth, UINT logicalHeight, int cmdShow) noexcept
    {
        m_title = title;

        WNDCLASSEXW wc{};
        wc.cbSize = sizeof(wc);
        wc.style = CS_HREDRAW | CS_VREDRAW;
        wc.lpfnWndProc = &D2DWindow::WindowProc;
        wc.hInstance = instance;
        wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
        wc.lpszClassName = kWindowClassName;

        if (RegisterClassExW(&wc) == 0 && GetLastError() != ERROR_CLASS_ALREADY_EXISTS)
        {
            return false;
        }

        const UINT initialDpi = GetDpiForSystem();
        RECT rc{
            0,
            0,
            static_cast<LONG>(MulDiv(static_cast<int>(logicalWidth), static_cast<int>(initialDpi), 96)),
            static_cast<LONG>(MulDiv(static_cast<int>(logicalHeight), static_cast<int>(initialDpi), 96))
        };
        AdjustWindowRectExForDpi(&rc, kWindowStyle, FALSE, kWindowExStyle, initialDpi);

        m_hwnd = CreateWindowExW(
            kWindowExStyle,
            kWindowClassName,
            m_title.c_str(),
            kWindowStyle,
            CW_USEDEFAULT,
            CW_USEDEFAULT,
            rc.right - rc.left,
            rc.bottom - rc.top,
            nullptr,
            nullptr,
            instance,
            this);

        if (m_hwnd == nullptr)
        {
            return false;
        }

        ApplyDwmAttributes();

        RECT clientRect{};
        GetClientRect(m_hwnd, &clientRect);
        const UINT widthPx = static_cast<UINT>(std::max<LONG>(1, clientRect.right - clientRect.left));
        const UINT heightPx = static_cast<UINT>(std::max<LONG>(1, clientRect.bottom - clientRect.top));

        if (FAILED(InitializeGraphics(widthPx, heightPx)))
        {
            DestroyWindow(m_hwnd);
            m_hwnd = nullptr;
            return false;
        }

        ShowWindow(m_hwnd, cmdShow);
        UpdateWindow(m_hwnd);
        return true;
    }

private:
    static constexpr wchar_t kWindowClassName[] = L"{{APP_NAME}}_{{APP_GUID}}_WndClass";
    static constexpr DWORD kWindowStyle = WS_OVERLAPPEDWINDOW;
    static constexpr DWORD kWindowExStyle = WS_EX_NOREDIRECTIONBITMAP;

    HWND m_hwnd = nullptr;
    std::wstring m_title;
    UINT m_widthPx = 1;
    UINT m_heightPx = 1;

    ComPtr<ID3D11Device> m_d3dDevice;
    ComPtr<IDXGIDevice> m_dxgiDevice;
    ComPtr<IDXGISwapChain1> m_swapChain;
    ComPtr<ID2D1Factory2> m_d2dFactory;
    ComPtr<ID2D1Device1> m_d2dDevice;
    ComPtr<ID2D1DeviceContext1> m_d2dContext;
    ComPtr<IDWriteFactory> m_dwriteFactory;
    ComPtr<IDWriteTextFormat> m_titleFormat;
    ComPtr<IDWriteTextFormat> m_bodyFormat;
    ComPtr<IDCompositionDevice> m_dcompDevice;
    ComPtr<IDCompositionTarget> m_dcompTarget;
    ComPtr<IDCompositionVisual> m_rootVisual;

    ComPtr<ID2D1SolidColorBrush> m_cardBrush;
    ComPtr<ID2D1SolidColorBrush> m_cardStrokeBrush;
    ComPtr<ID2D1SolidColorBrush> m_accentBrush;
    ComPtr<ID2D1SolidColorBrush> m_textPrimaryBrush;
    ComPtr<ID2D1SolidColorBrush> m_textSecondaryBrush;

    static LRESULT CALLBACK WindowProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) noexcept
    {
        D2DWindow* self = nullptr;
        if (msg == WM_NCCREATE)
        {
            const auto* cs = reinterpret_cast<const CREATESTRUCTW*>(lParam);
            self = static_cast<D2DWindow*>(cs->lpCreateParams);
            SetWindowLongPtrW(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(self));
            if (self != nullptr)
            {
                self->m_hwnd = hwnd;
            }
        }
        else
        {
            self = reinterpret_cast<D2DWindow*>(GetWindowLongPtrW(hwnd, GWLP_USERDATA));
        }

        if (self != nullptr)
        {
            return self->HandleMessage(msg, wParam, lParam);
        }

        return DefWindowProcW(hwnd, msg, wParam, lParam);
    }

    LRESULT HandleMessage(UINT msg, WPARAM wParam, LPARAM lParam) noexcept
    {
        switch (msg)
        {
        case WM_PAINT:
            OnPaint();
            return 0;

        case WM_SIZE:
            if (wParam != SIZE_MINIMIZED)
            {
                const UINT width = LOWORD(lParam);
                const UINT height = HIWORD(lParam);
                if (width > 0 && height > 0)
                {
                    OnResize(width, height);
                }
            }
            return 0;

        case WM_DPICHANGED:
        {
            const UINT dpi = HIWORD(wParam);
            const auto* suggested = reinterpret_cast<const RECT*>(lParam);
            SetWindowPos(
                m_hwnd,
                nullptr,
                suggested->left,
                suggested->top,
                suggested->right - suggested->left,
                suggested->bottom - suggested->top,
                SWP_NOZORDER | SWP_NOACTIVATE);
            if (m_d2dContext)
            {
                const float fDpi = static_cast<float>(dpi);
                m_d2dContext->SetDpi(fDpi, fDpi);
            }
            InvalidateRect(m_hwnd, nullptr, FALSE);
            return 0;
        }

        case WM_DESTROY:
            DiscardDeviceResources();
            PostQuitMessage(0);
            return 0;

        default:
            return DefWindowProcW(m_hwnd, msg, wParam, lParam);
        }
    }

    void ApplyDwmAttributes() const noexcept
    {
        const BOOL useDarkMode = TRUE;
        (void)DwmSetWindowAttribute(m_hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, &useDarkMode, sizeof(useDarkMode));

        const DWM_WINDOW_CORNER_PREFERENCE cornerPref = DWMWCP_ROUND;
        (void)DwmSetWindowAttribute(m_hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, &cornerPref, sizeof(cornerPref));
    }

    HRESULT InitializeGraphics(UINT widthPx, UINT heightPx) noexcept
    {
        m_widthPx = std::max<UINT>(1, widthPx);
        m_heightPx = std::max<UINT>(1, heightPx);

        HRESULT hr = CreateDeviceIndependentResources();
        if (FAILED(hr))
        {
            return hr;
        }

        return CreateDeviceResources();
    }

    HRESULT CreateDeviceIndependentResources() noexcept
    {
        if (!m_d2dFactory)
        {
            const HRESULT hr = D2D1CreateFactory(
                D2D1_FACTORY_TYPE_SINGLE_THREADED,
                __uuidof(ID2D1Factory2),
                nullptr,
                &m_d2dFactory);
            if (FAILED(hr))
            {
                return hr;
            }
        }

        if (!m_dwriteFactory)
        {
            const HRESULT hr = DWriteCreateFactory(
                DWRITE_FACTORY_TYPE_SHARED,
                __uuidof(IDWriteFactory),
                reinterpret_cast<IUnknown**>(m_dwriteFactory.GetAddressOf()));
            if (FAILED(hr))
            {
                return hr;
            }
        }

        if (!m_titleFormat)
        {
            const HRESULT hr = m_dwriteFactory->CreateTextFormat(
                L"Segoe UI Variable Text",
                nullptr,
                DWRITE_FONT_WEIGHT_SEMI_BOLD,
                DWRITE_FONT_STYLE_NORMAL,
                DWRITE_FONT_STRETCH_NORMAL,
                28.0f,
                L"",
                &m_titleFormat);
            if (FAILED(hr))
            {
                return hr;
            }
        }

        if (!m_bodyFormat)
        {
            const HRESULT hr = m_dwriteFactory->CreateTextFormat(
                L"Segoe UI Variable Text",
                nullptr,
                DWRITE_FONT_WEIGHT_REGULAR,
                DWRITE_FONT_STYLE_NORMAL,
                DWRITE_FONT_STRETCH_NORMAL,
                14.0f,
                L"",
                &m_bodyFormat);
            if (FAILED(hr))
            {
                return hr;
            }
        }

        return S_OK;
    }

    HRESULT CreateDeviceResources() noexcept
    {
        if (m_d2dContext)
        {
            return S_OK;
        }

        const UINT flags = D3D11_CREATE_DEVICE_BGRA_SUPPORT;
        HRESULT hr = D3D11CreateDevice(
            nullptr,
            D3D_DRIVER_TYPE_HARDWARE,
            nullptr,
            flags,
            nullptr,
            0,
            D3D11_SDK_VERSION,
            &m_d3dDevice,
            nullptr,
            nullptr);

        if (FAILED(hr))
        {
            hr = D3D11CreateDevice(
                nullptr,
                D3D_DRIVER_TYPE_WARP,
                nullptr,
                flags,
                nullptr,
                0,
                D3D11_SDK_VERSION,
                &m_d3dDevice,
                nullptr,
                nullptr);
            if (FAILED(hr))
            {
                return hr;
            }
        }

        hr = m_d3dDevice.As(&m_dxgiDevice);
        if (FAILED(hr))
        {
            return hr;
        }

        ComPtr<IDXGIAdapter> adapter;
        ComPtr<IDXGIFactory2> dxgiFactory;
        hr = m_dxgiDevice->GetAdapter(&adapter);
        if (FAILED(hr))
        {
            return hr;
        }

        hr = adapter->GetParent(IID_PPV_ARGS(&dxgiFactory));
        if (FAILED(hr))
        {
            return hr;
        }

        DXGI_SWAP_CHAIN_DESC1 desc{};
        desc.Width = m_widthPx;
        desc.Height = m_heightPx;
        desc.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
        desc.SampleDesc.Count = 1;
        desc.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
        desc.BufferCount = 2;
        desc.Scaling = DXGI_SCALING_STRETCH;
        desc.SwapEffect = DXGI_SWAP_EFFECT_FLIP_SEQUENTIAL;
        desc.AlphaMode = DXGI_ALPHA_MODE_PREMULTIPLIED;

        hr = dxgiFactory->CreateSwapChainForComposition(m_dxgiDevice.Get(), &desc, nullptr, &m_swapChain);
        if (FAILED(hr))
        {
            return hr;
        }

        hr = m_d2dFactory->CreateDevice(m_dxgiDevice.Get(), &m_d2dDevice);
        if (FAILED(hr))
        {
            return hr;
        }

        hr = m_d2dDevice->CreateDeviceContext(D2D1_DEVICE_CONTEXT_OPTIONS_NONE, &m_d2dContext);
        if (FAILED(hr))
        {
            return hr;
        }

        hr = DCompositionCreateDevice(m_dxgiDevice.Get(), IID_PPV_ARGS(&m_dcompDevice));
        if (FAILED(hr))
        {
            return hr;
        }

        hr = m_dcompDevice->CreateTargetForHwnd(m_hwnd, TRUE, &m_dcompTarget);
        if (FAILED(hr))
        {
            return hr;
        }

        hr = m_dcompDevice->CreateVisual(&m_rootVisual);
        if (FAILED(hr))
        {
            return hr;
        }

        hr = m_rootVisual->SetContent(m_swapChain.Get());
        if (FAILED(hr))
        {
            return hr;
        }

        hr = m_dcompTarget->SetRoot(m_rootVisual.Get());
        if (FAILED(hr))
        {
            return hr;
        }

        hr = m_dcompDevice->Commit();
        if (FAILED(hr))
        {
            return hr;
        }

        hr = m_d2dContext->CreateSolidColorBrush(D2D1::ColorF(0x1C212B, 1.0f), &m_cardBrush);
        if (FAILED(hr))
        {
            return hr;
        }

        hr = m_d2dContext->CreateSolidColorBrush(D2D1::ColorF(0x2E3646, 1.0f), &m_cardStrokeBrush);
        if (FAILED(hr))
        {
            return hr;
        }

        hr = m_d2dContext->CreateSolidColorBrush(D2D1::ColorF(0x3B82F6, 1.0f), &m_accentBrush);
        if (FAILED(hr))
        {
            return hr;
        }

        hr = m_d2dContext->CreateSolidColorBrush(D2D1::ColorF(0xF8FAFC, 1.0f), &m_textPrimaryBrush);
        if (FAILED(hr))
        {
            return hr;
        }

        hr = m_d2dContext->CreateSolidColorBrush(D2D1::ColorF(0xCBD5E1, 1.0f), &m_textSecondaryBrush);
        if (FAILED(hr))
        {
            return hr;
        }

        const float dpi = static_cast<float>(GetDpiForWindow(m_hwnd));
        return BindBackBufferTarget(dpi);
    }

    HRESULT BindBackBufferTarget(float dpi) noexcept
    {
        ComPtr<IDXGISurface2> surface;
        HRESULT hr = m_swapChain->GetBuffer(0, IID_PPV_ARGS(&surface));
        if (FAILED(hr))
        {
            return hr;
        }

        const D2D1_BITMAP_PROPERTIES1 props = D2D1::BitmapProperties1(
            D2D1_BITMAP_OPTIONS_TARGET | D2D1_BITMAP_OPTIONS_CANNOT_DRAW,
            D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM, D2D1_ALPHA_MODE_PREMULTIPLIED),
            dpi,
            dpi);

        ComPtr<ID2D1Bitmap1> targetBitmap;
        hr = m_d2dContext->CreateBitmapFromDxgiSurface(surface.Get(), &props, &targetBitmap);
        if (FAILED(hr))
        {
            return hr;
        }

        m_d2dContext->SetTarget(targetBitmap.Get());
        m_d2dContext->SetDpi(dpi, dpi);
        return S_OK;
    }

    void DiscardDeviceResources() noexcept
    {
        m_cardBrush.Reset();
        m_cardStrokeBrush.Reset();
        m_accentBrush.Reset();
        m_textPrimaryBrush.Reset();
        m_textSecondaryBrush.Reset();
        m_rootVisual.Reset();
        m_dcompTarget.Reset();
        m_dcompDevice.Reset();
        m_d2dContext.Reset();
        m_d2dDevice.Reset();
        m_swapChain.Reset();
        m_dxgiDevice.Reset();
        m_d3dDevice.Reset();
    }

    void OnResize(UINT widthPx, UINT heightPx) noexcept
    {
        m_widthPx = std::max<UINT>(1, widthPx);
        m_heightPx = std::max<UINT>(1, heightPx);

        if (!m_d2dContext || !m_swapChain)
        {
            return;
        }

        m_d2dContext->SetTarget(nullptr);
        const HRESULT hr = m_swapChain->ResizeBuffers(0, m_widthPx, m_heightPx, DXGI_FORMAT_UNKNOWN, 0);
        if (hr == DXGI_ERROR_DEVICE_REMOVED || hr == DXGI_ERROR_DEVICE_RESET)
        {
            DiscardDeviceResources();
            return;
        }

        const float dpi = static_cast<float>(GetDpiForWindow(m_hwnd));
        if (SUCCEEDED(BindBackBufferTarget(dpi)))
        {
            (void)m_dcompDevice->Commit();
            InvalidateRect(m_hwnd, nullptr, FALSE);
        }
    }

    void OnPaint() noexcept
    {
        if (FAILED(CreateDeviceResources()))
        {
            ValidateRect(m_hwnd, nullptr);
            return;
        }

        const D2D1_SIZE_F dipSize = m_d2dContext->GetSize();

        m_d2dContext->BeginDraw();
        m_d2dContext->Clear(D2D1::ColorF(0x11151C, 1.0f));

        const float margin = 24.0f;
        const float cardWidth = std::max(160.0f, dipSize.width - margin * 2.0f);
        const float cardHeight = std::max(120.0f, dipSize.height - margin * 2.0f);
        const D2D1_ROUNDED_RECT cardRect = D2D1::RoundedRect(
            D2D1::RectF(margin, margin, margin + cardWidth, margin + cardHeight),
            8.0f,
            8.0f);

        m_d2dContext->FillRoundedRectangle(cardRect, m_cardBrush.Get());
        m_d2dContext->DrawRoundedRectangle(cardRect, m_cardStrokeBrush.Get(), 1.0f);

        const D2D1_ELLIPSE badge = D2D1::Ellipse(D2D1::Point2F(margin + 36.0f, margin + 40.0f), 12.0f, 12.0f);
        m_d2dContext->FillEllipse(badge, m_accentBrush.Get());

        const D2D1_RECT_F titleRect = D2D1::RectF(
            margin + 60.0f,
            margin + 22.0f,
            margin + cardWidth - 24.0f,
            margin + 64.0f);
        m_d2dContext->DrawTextW(
            m_title.c_str(),
            static_cast<UINT32>(m_title.size()),
            m_titleFormat.Get(),
            titleRect,
            m_textPrimaryBrush.Get());

        constexpr std::wstring_view subtitle =
            L"Zero-.NET native Windows desktop starter (Direct2D + DirectComposition + PerMonitorV2 DPI).";
        const D2D1_RECT_F bodyRect = D2D1::RectF(
            margin + 24.0f,
            margin + 80.0f,
            margin + cardWidth - 24.0f,
            margin + cardHeight - 24.0f);
        m_d2dContext->DrawTextW(
            subtitle.data(),
            static_cast<UINT32>(subtitle.size()),
            m_bodyFormat.Get(),
            bodyRect,
            m_textSecondaryBrush.Get());

        HRESULT hr = m_d2dContext->EndDraw();
        if (hr == D2DERR_RECREATE_TARGET)
        {
            DiscardDeviceResources();
        }
        else if (SUCCEEDED(hr))
        {
            hr = m_swapChain->Present(1, 0);
            if (hr == DXGI_ERROR_DEVICE_REMOVED || hr == DXGI_ERROR_DEVICE_RESET)
            {
                DiscardDeviceResources();
            }
        }

        ValidateRect(m_hwnd, nullptr);
    }
};
} // namespace {{APP_NAME}}_native
