import { useState } from 'react';
import {
  AUDITOR_OUTPUTS,
  COMPILER_TRAPS,
  GUIDE_DOCS,
  STACK_SPECS,
  type Lang,
} from '../data/skillData';
import './LandingPage.css';

interface Props {
  lang: Lang;
  onToggleLang: () => void;
}

const INSTALL_TABS = [
  { id: 'cli', label: 'Skills CLI', cmd: 'npx skills add Destro01400/windows-native' },
  {
    id: 'agy',
    label: 'Antigravity',
    cmd: 'git clone https://github.com/Destro01400/windows-native.git .agent/skills/windows-native',
  },
  {
    id: 'claude',
    label: 'Claude Code',
    cmd: 'git clone https://github.com/Destro01400/windows-native.git .claude/skills/windows-native',
  },
  {
    id: 'codex',
    label: 'Codex',
    cmd: 'git clone https://github.com/Destro01400/windows-native.git .agents/skills/windows-native',
  },
  {
    id: 'opencode',
    label: 'OpenCode',
    cmd: 'git clone https://github.com/Destro01400/windows-native.git .opencode/skills/windows-native',
  },
];

export function LandingPage({ lang, onToggleLang }: Props) {
  const [installTab, setInstallTab] = useState(INSTALL_TABS[0]);
  const [footerInstallTab, setFooterInstallTab] = useState(INSTALL_TABS[0]);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [activeTrapId, setActiveTrapId] = useState(COMPILER_TRAPS[0].id);
  const [activeStackId, setActiveStackId] = useState(STACK_SPECS[0].id);
  const [guideFilter, setGuideFilter] = useState<'all' | 'arch' | 'ui' | 'native' | 'ship'>('all');
  const [auditorMode, setAuditorMode] = useState<'full' | 'clean'>('full');

  const activeTrap = COMPILER_TRAPS.find((t) => t.id === activeTrapId) ?? COMPILER_TRAPS[0];
  const activeStack = STACK_SPECS.find((s) => s.id === activeStackId) ?? STACK_SPECS[0];
  const visibleGuides =
    guideFilter === 'all' ? GUIDE_DOCS : GUIDE_DOCS.filter((g) => g.category === guideFilter);
  const activeAudit = AUDITOR_OUTPUTS[auditorMode];

  const copyText = async (id: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      window.setTimeout(() => setCopiedId((cur) => (cur === id ? null : cur)), 1600);
    } catch {
      setCopiedId(null);
    }
  };

  return (
    <div className="site-shell">
      <header className="site-nav">
        <div className="container site-nav__inner">
          <a href="#top" className="brand-lockup">
            <span className="brand-mark" aria-hidden="true">
              <span />
              <span />
              <span />
              <span />
            </span>
            <span>windows-native</span>
          </a>

          <nav className="site-nav__links" aria-label="Main navigation">
            <a href="#stacks">Stacks</a>
            <a href="#pillars">{lang === 'pt' ? 'Engenharia' : 'Engineering'}</a>
            <a href="#guides">{lang === 'pt' ? 'Guias (10)' : 'Guides (10)'}</a>
            <a href="#auditor">Auditor</a>
            <a href="#install">{lang === 'pt' ? 'Instalar' : 'Install'}</a>
          </nav>

          <div className="site-nav__tools">
            <button type="button" className="nav-btn" onClick={onToggleLang}>
              {lang === 'pt' ? 'EN' : 'PT-BR'}
            </button>
            <a
              className="nav-btn nav-btn--primary"
              href="https://github.com/Destro01400/windows-native"
              target="_blank"
              rel="noreferrer"
            >
              GitHub ↗
            </a>
          </div>
        </div>
      </header>

      <main id="top">
        {/* 1. HERO */}
        <section className="hero-band">
          <div className="container hero-grid">
            <div>
              <span className="eyebrow">AGENT SKILL · WINDOWS 10 / 11 · MIT</span>

              <h1 className="hero-title">
                {lang === 'pt' ? (
                  <>
                    Construa apps Windows <em className="em-italic">nativos de verdade</em>.
                  </>
                ) : (
                  <>
                    Build <em className="em-italic">real native</em> Windows apps.
                  </>
                )}
              </h1>

              <p className="hero-lead">
                {lang === 'pt'
                  ? 'Skill completa para agentes de código projetarem, arquitetarem, compilarem, assinarem e auditarem aplicativos Windows 10/11 em WPF (.NET 9/10), WinUI 3 + NativeAOT, C++/WinRT e CsWin32 — sem erros de compilação inventados.'
                  : 'An end-to-end engineering skill for coding agents building Windows 10/11 apps across WPF (.NET 9/10), WinUI 3 + NativeAOT, C++/WinRT, and CsWin32—from Fluent 2 motion and Snap Layouts to MSIX, Velopack, and code signing.'}
              </p>

              <div className="install-box">
                <div className="install-box__tabs" role="tablist" aria-label="Install method">
                  {INSTALL_TABS.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      role="tab"
                      aria-selected={installTab.id === t.id}
                      className={`install-tab ${installTab.id === t.id ? 'is-active' : ''}`}
                      onClick={() => setInstallTab(t)}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
                <div className="install-box__cmd">
                  <code>$ {installTab.cmd}</code>
                  <button
                    type="button"
                    className={`copy-mini ${copiedId === 'hero' ? 'is-copied' : ''}`}
                    onClick={() => copyText('hero', installTab.cmd)}
                  >
                    {copiedId === 'hero'
                      ? lang === 'pt'
                        ? 'Copiado'
                        : 'Copied'
                      : lang === 'pt'
                        ? 'Copiar'
                        : 'Copy'}
                  </button>
                </div>
              </div>

              <div className="hero-metrics">
                <div>
                  <div className="metric-val">10</div>
                  <div className="metric-lbl">
                    {lang === 'pt' ? 'Guias modulares' : 'Modular reference guides'}
                  </div>
                </div>
                <div>
                  <div className="metric-val">2</div>
                  <div className="metric-lbl">
                    {lang === 'pt' ? 'Auditores Python' : 'Zero-dep Python auditors'}
                  </div>
                </div>
                <div>
                  <div className="metric-val">0</div>
                  <div className="metric-lbl">
                    {lang === 'pt' ? 'Erros no .NET 10 & MSVC' : 'Errors on .NET 10 & MSVC'}
                  </div>
                </div>
              </div>
            </div>

            {/* Native Win11 Frame Window Preview */}
            <aside className="win11-frame" aria-label="Compiler trap inspector">
              <div className="win11-caption">
                <div className="win11-caption__title">
                  <span className="win11-caption__dot" aria-hidden="true" />
                  <span>CompilerVerify.xaml — {activeTrap.code}</span>
                </div>
                <div className="win11-caption__controls" aria-hidden="true">
                  <span className="win11-caption__btn">─</span>
                  <span className="win11-caption__btn win11-caption__btn--max">□</span>
                  <span className="win11-caption__btn">×</span>
                </div>
              </div>

              <div className="trap-panel__pills">
                {COMPILER_TRAPS.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    className={`trap-pill ${activeTrap.id === t.id ? 'is-active' : ''}`}
                    onClick={() => setActiveTrapId(t.id)}
                  >
                    {t.code}
                  </button>
                ))}
              </div>

              <div className="trap-code-split">
                <div className="trap-block">
                  <span className="trap-block__tag trap-block__tag--bad">
                    {lang === 'pt' ? `Quebra no build (${activeTrap.code})` : `Fails build (${activeTrap.code})`}
                  </span>
                  <pre>{activeTrap.broken}</pre>
                </div>
                <div className="trap-block">
                  <span className="trap-block__tag trap-block__tag--good">
                    {lang === 'pt' ? 'Padrão compilado na skill' : 'Verified skill fix'}
                  </span>
                  <pre>{activeTrap.fixed}</pre>
                </div>
              </div>

              <div className="trap-why">{activeTrap.why[lang]}</div>
            </aside>
          </div>
        </section>

        {/* 2. STACK EXPLORER */}
        <section id="stacks" className="band band--recessed">
          <div className="container">
            <div className="band-head">
              <span className="eyebrow">
                {lang === 'pt' ? '01 · MATRIZ DE TECNOLOGIAS' : '01 · NATIVE STACK MATRIX'}
              </span>
              <h2>
                {lang === 'pt' ? (
                  <>
                    Escolha a base certa para <em className="em-italic">cada aplicativo</em>.
                  </>
                ) : (
                  <>
                    Pick the right foundation for <em className="em-italic">each Windows app</em>.
                  </>
                )}
              </h2>
              <p>
                {lang === 'pt'
                  ? 'Compare arquitetura, compilação AOT, threading e bindings reais entre os 4 caminhos cobertos pela skill.'
                  : 'Inspect build targets, NativeAOT eligibility, threading models, and verified code patterns across all four supported paths.'}
              </p>
            </div>

            <div className="stack-tabs" role="tablist">
              {STACK_SPECS.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  role="tab"
                  aria-selected={activeStack.id === s.id}
                  className={`stack-tab ${activeStack.id === s.id ? 'is-active' : ''}`}
                  onClick={() => setActiveStackId(s.id)}
                >
                  {s.name}
                </button>
              ))}
            </div>

            <div className="stack-panel">
              <div className="stack-panel__info">
                <div>
                  <span className="eyebrow">{activeStack.badge}</span>
                  <h3 style={{ marginTop: '8px' }}>{activeStack.name}</h3>
                </div>
                <p>{activeStack.summary[lang]}</p>
                <div className="stack-kv">
                  {activeStack.metrics.map((m) => (
                    <div key={m.label.en}>
                      <div className="stack-kv__k">{m.label[lang]}</div>
                      <div className="stack-kv__v">{m.value}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="stack-panel__code">
                <div className="stack-panel__code-title">{activeStack.snippetTitle}</div>
                <pre>{activeStack.snippet}</pre>
              </div>
            </div>
          </div>
        </section>

        {/* 3. ENGINEERING PILLARS */}
        <section id="pillars" className="band">
          <div className="container">
            <div className="band-head">
              <span className="eyebrow">
                {lang === 'pt' ? '02 · COBERTURA DE PONTA A PONTA' : '02 · END-TO-END COVERAGE'}
              </span>
              <h2>
                {lang === 'pt' ? (
                  <>
                    Do ciclo de vida ao <em className="em-italic">instalador assinado</em>.
                  </>
                ) : (
                  <>
                    From app lifecycle to a <em className="em-italic">trusted release</em>.
                  </>
                )}
              </h2>
              <p>
                {lang === 'pt'
                  ? 'Em vez de ficar só no visual, a Skill windows-native cobre as camadas que costumam quebrar aplicativos Windows em produção.'
                  : 'Instead of stopping at layout tweaks, the windows-native skill covers the production systems where desktop apps usually break.'}
              </p>
            </div>

            <div className="pillars-grid">
              <article className="pillar-card">
                <span className="pillar-card__num">01 · ARCHITECTURE &amp; LIFECYCLE</span>
                <h3>{lang === 'pt' ? 'Startup, IPC & Persistência' : 'Startup, IPC & Safe State'}</h3>
                <p>
                  {lang === 'pt'
                    ? 'Injeção de dependência e sobrevivência a quedas de energia ou sessões encerradas.'
                    : 'Clean Host DI wiring and crash-resilient persistence for desktop processes.'}
                </p>
                <ul>
                  <li>Generic Host + CultureInfo XmlLanguage + StartupUri removal</li>
                  <li>Atomic %LocalAppData% writes (Flush + File.Replace) &amp; SQLite WAL</li>
                  <li>Mutex + GC.KeepAlive + CurrentUserOnly Named Pipes + URI &quot;%1&quot; safety</li>
                  <li>WER RegisterApplicationRestart &amp; async buffered Serilog sinks</li>
                </ul>
              </article>

              <article className="pillar-card">
                <span className="pillar-card__num">02 · WINDOWS OS &amp; CSWIN32</span>
                <h3>{lang === 'pt' ? 'Interop Moderna & Segurança' : 'Modern OS Interop & Security'}</h3>
                <p>
                  {lang === 'pt'
                    ? 'Acesso às APIs nativas do Windows sem vazamentos nem segredos expostos.'
                    : 'Type-safe Win32/COM bindings, secrets protection, and hardware event discipline.'}
                </p>
                <ul>
                  <li>CsWin32 NativeMethods.txt/.json + SafeHandle Lease() rules</li>
                  <li>DPAPI CurrentUser with entropy, Credential Manager &amp; PasswordVault</li>
                  <li>app.manifest (PerMonitorV2, Win10/11 GUIDs, longPathAware, UTF-8)</li>
                  <li>RegisterHotKey, OpenFolderDialog, WASAPI/NAudio &amp; PowerModeChanged -=</li>
                </ul>
              </article>

              <article className="pillar-card">
                <span className="pillar-card__num">03 · UI, CHROME &amp; IGPU MOTION</span>
                <h3>{lang === 'pt' ? 'Design Nativo, DWM & 60 FPS' : 'Native Chrome, Fluent 2 & Motion'}</h3>
                <p>
                  {lang === 'pt'
                    ? 'Interface coerente com Windows 11, leve em GPU integrada e acessível por teclado.'
                    : 'Genuine Windows 11 window physics, WCAG AA contrast, and integrated-GPU animation.'}
                </p>
                <ul>
                  <li>WindowChrome without AllowsTransparency + full HTMAXBUTTON Snap Layouts</li>
                  <li>Fluent 2 KeySplines (83/167/250 ms), VSM, ClientAreaAnimation reduced motion</li>
                  <li>po:Freeze=&quot;True&quot;, VirtualizingStackPanel &amp; 20–30 Hz streaming batching</li>
                  <li>UI Automation parity (AutomationProperties.Name, IsKeyboardFocusWithin)</li>
                </ul>
              </article>

              <article className="pillar-card">
                <span className="pillar-card__num">04 · PACKAGING, SIGNING &amp; QA</span>
                <h3>{lang === 'pt' ? 'Entrega, Assinatura & Profiling' : 'Shipping, Signing & Profiling'}</h3>
                <p>
                  {lang === 'pt'
                    ? 'Publicação profissional evitando alertas do SmartScreen e regressões invisíveis.'
                    : 'Production distribution, Authenticode trust, and live memory/frame profiling.'}
                </p>
                <ul>
                  <li>Single-File WPF vs. PublishReadyToRun vs. WinUI 3 / Win32 NativeAOT</li>
                  <li>MSIX &amp; External Location Sparse Packages (ComServer + MakeAppx /nv)</li>
                  <li>WiX Toolset v5, Inno Setup 6, Velopack delta updates &amp; Azure Artifact Signing</li>
                  <li>xUnit + [WpfFact] + FlaUI.UIA3, WER LocalDumps, dotnet-dump &amp; WPR/WPA</li>
                </ul>
              </article>
            </div>
          </div>
        </section>

        {/* 4. GUIDES CATALOG */}
        <section id="guides" className="band band--recessed">
          <div className="container">
            <div className="band-head">
              <span className="eyebrow">
                {lang === 'pt' ? '03 · BIBLIOTECA MODULAR' : '03 · PROGRESSIVE-DISCLOSURE LIBRARY'}
              </span>
              <h2>
                {lang === 'pt' ? (
                  <>
                    10 referências focadas — carregue <em className="em-italic">só o necessário</em>.
                  </>
                ) : (
                  <>
                    10 focused references — load <em className="em-italic">only what fits</em>.
                  </>
                )}
              </h2>
              <p>
                {lang === 'pt'
                  ? 'O SKILL.md tem 82 linhas e direciona o agente apenas para o módulo exato da tarefa atual, economizando contexto.'
                  : 'SKILL.md stays compact (82 lines) and routes agents strictly to the domain guide needed for the active task.'}
              </p>
            </div>

            <div className="guide-filters">
              {(
                [
                  ['all', lang === 'pt' ? 'Todos (10)' : 'All (10)'],
                  ['arch', lang === 'pt' ? 'Arquitetura & OS (2)' : 'Architecture & OS (2)'],
                  ['native', 'WinUI 3 & C++ (1)'],
                  ['ui', lang === 'pt' ? 'UI, Chrome & Motion (5)' : 'UI, Chrome & Motion (5)'],
                  ['ship', lang === 'pt' ? 'Build, Testes & Profiling (2)' : 'Packaging & QA (2)'],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  className={`filter-pill ${guideFilter === key ? 'is-active' : ''}`}
                  onClick={() => setGuideFilter(key)}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="guides-list">
              {visibleGuides.map((g) => (
                <a
                  key={g.file}
                  className="guide-row"
                  href={`https://github.com/Destro01400/windows-native/blob/main/references/${g.file}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <div>
                    <div className="guide-row__title">{g.title[lang]}</div>
                    <div className="guide-row__file">references/{g.file}</div>
                  </div>
                  <div className="guide-row__desc">{g.desc[lang]}</div>
                  <div className="guide-row__meta">
                    <span>{g.lines} lines</span>
                    <span>↗</span>
                  </div>
                </a>
              ))}
            </div>
          </div>
        </section>

        {/* 5. STATIC AUDITOR & DIAGNOSTICS */}
        <section id="auditor" className="band">
          <div className="container">
            <div className="band-head">
              <span className="eyebrow">
                {lang === 'pt' ? '04 · AUDITOR ESTÁTICO SEM DEPENDÊNCIAS' : '04 · ZERO-DEPENDENCY STATIC AUDITOR'}
              </span>
              <h2>
                {lang === 'pt' ? (
                  <>
                    Inspecione o app inteiro com <em className="em-italic">um único comando</em>.
                  </>
                ) : (
                  <>
                    Audit `.csproj`, manifests &amp; XAML in <em className="em-italic">one command</em>.
                  </>
                )}
              </h2>
              <p>
                {lang === 'pt'
                  ? 'scripts/audit_windows_app.py roda em Python puro com modos --strict, --json e --ui-only (mantendo audit_wpf_ui.py compatível).'
                  : 'scripts/audit_windows_app.py runs on stock Python with --strict, --json, and --ui-only modes alongside backwards-compatible audit_wpf_ui.py.'}
              </p>
            </div>

            <div className="auditor-grid">
              <div className="terminal-card">
                <div className="terminal-card__bar">
                  <span>$ {activeAudit.cmd}</span>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      type="button"
                      className={`nav-btn ${auditorMode === 'full' ? 'nav-btn--primary' : ''}`}
                      onClick={() => setAuditorMode('full')}
                    >
                      {lang === 'pt' ? 'Exemplo c/ Falhas' : 'Sample Issues'}
                    </button>
                    <button
                      type="button"
                      className={`nav-btn ${auditorMode === 'clean' ? 'nav-btn--primary' : ''}`}
                      onClick={() => setAuditorMode('clean')}
                    >
                      {lang === 'pt' ? 'JSON Limpo' : 'Clean JSON'}
                    </button>
                  </div>
                </div>
                <div className="terminal-card__body">
                  {activeAudit.lines.map((line, i) => (
                    <div
                      key={i}
                      className={
                        line.kind === 'err'
                          ? 't-err'
                          : line.kind === 'warn'
                            ? 't-warn'
                            : line.kind === 'ok'
                              ? 't-ok'
                              : 't-dim'
                      }
                    >
                      {line.text}
                    </div>
                  ))}
                </div>
              </div>

              <div className="qa-stack">
                <div className="qa-item">
                  <div className="qa-item__k">1. Compiler Verification</div>
                  <p>
                    {lang === 'pt'
                      ? 'Exemplos WPF, CsWin32, Velopack, WinUI 3 e C++/WinRT validados com TreatWarningsAsErrors no .NET 10.0.302, Windows SDK 10.0.26100 e MSVC.'
                      : 'Core WPF, CsWin32, Velopack, WinUI 3 + PublishAot, Sparse Package MakeAppx, and C++/WinRT + WIL snippets compiled with zero errors/warnings.'}
                  </p>
                </div>
                <div className="qa-item">
                  <div className="qa-item__k">2. Full App + UI Checks</div>
                  <p>
                    {lang === 'pt'
                      ? 'Detecta NETSDK1168, falta de AllowUnsafeBlocks, Mutex sem GC.KeepAlive, ProcessStartInfo vulnerável, contraste abaixo de 4.5:1 e loops Forever invisíveis.'
                      : 'Catches NETSDK1168, missing AllowUnsafeBlocks, un-pinned Mutex, unsafe ProcessStartInfo strings, WCAG < 4.5:1 contrast, and leaked CompositionTarget loops.'}
                  </p>
                </div>
                <div className="qa-item">
                  <div className="qa-item__k">3. CI &amp; Crash Diagnostics</div>
                  <p>
                    {lang === 'pt'
                      ? 'Pronto para GitHub Actions (--strict --json) e combinado com WER LocalDumps, dotnet-dump gcroot e traces DWM no Windows Performance Analyzer.'
                      : 'Drop --strict --json straight into CI pipelines and pair with WER LocalDumps, dotnet-dump gcroot, and Windows Performance Analyzer.'}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* 6. INSTALL & FOOTER */}
        <footer id="install" className="site-footer band--recessed">
          <div className="container">
            <div className="footer-grid">
              <div style={{ width: 'min(740px, 100%)' }}>
                <span className="eyebrow">INSTALL WINDOWS-NATIVE</span>
                <h2 style={{ fontSize: 'clamp(2.2rem, 4vw, 3.3rem)', marginTop: '10px' }}>
                  {lang === 'pt' ? 'Pronto para usar no seu projeto.' : 'Ready to drop into your agent setup.'}
                </h2>
                <div className="install-box">
                  <div className="install-box__tabs" role="tablist" aria-label="Footer install method">
                    {INSTALL_TABS.map((t) => (
                      <button
                        key={t.id}
                        type="button"
                        role="tab"
                        aria-selected={footerInstallTab.id === t.id}
                        className={`install-tab ${footerInstallTab.id === t.id ? 'is-active' : ''}`}
                        onClick={() => setFooterInstallTab(t)}
                      >
                        {t.label}
                      </button>
                    ))}
                  </div>
                  <div className="install-box__cmd">
                    <code>$ {footerInstallTab.cmd}</code>
                    <button
                      type="button"
                      className={`copy-mini ${copiedId === 'footer' ? 'is-copied' : ''}`}
                      onClick={() => copyText('footer', footerInstallTab.cmd)}
                    >
                      {copiedId === 'footer'
                        ? lang === 'pt'
                          ? 'Copiado'
                          : 'Copied'
                        : lang === 'pt'
                          ? 'Copiar'
                          : 'Copy'}
                    </button>
                  </div>
                </div>
              </div>

              <div className="footer-links">
                <a
                  href="https://github.com/Destro01400/windows-native"
                  target="_blank"
                  rel="noreferrer"
                >
                  Repository ↗
                </a>
                <a
                  href="https://github.com/Destro01400/windows-native/blob/main/SKILL.md"
                  target="_blank"
                  rel="noreferrer"
                >
                  SKILL.md ↗
                </a>
                <a
                  href="https://github.com/Destro01400/windows-native/blob/main/LICENSE"
                  target="_blank"
                  rel="noreferrer"
                >
                  MIT License
                </a>
              </div>
            </div>
          </div>
        </footer>
      </main>
    </div>
  );
}
