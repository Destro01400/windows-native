import { useState } from 'react';
import type { Lang } from './data/skillData';
import { LandingPage } from './components/LandingPage';

function getInitialLang(): Lang {
  if (typeof window === 'undefined') return 'en';
  const param = new URLSearchParams(window.location.search).get('lang');
  if (param === 'pt' || param === 'en') return param;
  const saved = window.localStorage.getItem('wn-lang');
  if (saved === 'pt' || saved === 'en') return saved;
  return navigator.language.toLowerCase().startsWith('pt') ? 'pt' : 'en';
}

function App() {
  const [lang, setLang] = useState<Lang>(getInitialLang);

  const toggleLang = () => {
    setLang((prev) => {
      const next: Lang = prev === 'pt' ? 'en' : 'pt';
      window.localStorage.setItem('wn-lang', next);
      return next;
    });
  };

  return <LandingPage lang={lang} onToggleLang={toggleLang} />;
}

export default App;
