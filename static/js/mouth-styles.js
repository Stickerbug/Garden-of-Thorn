/* 嘴型款式的共享目录与叠加贴图：主站、故事模式、合成小游戏共用。 */
(() => {
  const definitions = Object.freeze([
    Object.freeze({ id: 'cat', asset: '/static/assets/mouth-styles/cat.svg', names: Object.freeze({ zh: 'w嘴', en: 'W Mouth', fr: 'Bouche en W', ja: 'Wの口' }) }),
    Object.freeze({ id: 'smirk', asset: '/static/assets/mouth-styles/smirk.svg', names: Object.freeze({ zh: '歪嘴', en: 'Smirk', fr: 'Sourire oblique', ja: '歪んだ口' }) }),
    Object.freeze({ id: 'open', asset: '/static/assets/mouth-styles/open.svg', names: Object.freeze({ zh: '张口', en: 'Open Mouth', fr: 'Bouche ouverte', ja: '開いた口' }) }),
    Object.freeze({ id: 'angry', asset: '/static/assets/mouth-styles/angry.svg', names: Object.freeze({ zh: '愤怒', en: 'Angry', fr: 'Colère', ja: '怒り' }) }),
  ]);
  const byId = new Map(definitions.map(item => [item.id, item]));

  function normalize(value) {
    const id = String(value || '').trim().toLowerCase();
    return byId.has(id) ? id : 'original';
  }
  function get(value) { return byId.get(normalize(value)) || null; }
  function url(value) { return get(value)?.asset || ''; }
  function render(value) {
    const definition = get(value);
    return definition ? `<img class="skin-mouth-art skin-mouth-art-${definition.id}" src="${definition.asset}" alt="" aria-hidden="true" draggable="false">` : '';
  }

  window.GTNMouthStyles = Object.freeze({ definitions, normalize, get, url, render });
})();
