/* 眼睛款式的共享目录与叠加贴图：主站、故事模式、合成小游戏共用。 */
(() => {
  const ANGRY_SOCKET_PATHS = Object.freeze([
    'M121.9,142.2c0,15.7-6.3,28.3-14.2,28.3s-14.2-12.7-14.2-28.3,8.6-33.9,14.2-28.3c14.5,14.4,14.2,12.7,14.2,28.3Z',
    'M189.9,142.2c0,15.7-6.3,28.3-14.2,28.3s-14.2-12.7-14.2-28.3-.2-14,14.2-28.3c5.5-5.5,14.2,12.7,14.2,28.3Z',
  ]);
  const definitions = Object.freeze([
    Object.freeze({
      id: 'angry', asset: '/static/assets/eye-styles/angry.svg',
      socketAsset: '/static/assets/eye-styles/angry-socket.svg',
      whiteAsset: '/static/assets/eye-styles/angry-white.svg',
      clipPaths: ANGRY_SOCKET_PATHS, viewBox: 283.5,
      names: Object.freeze({ zh: '愤怒', en: 'Angry', fr: 'Colère', ja: '怒り' }),
    }),
    Object.freeze({ id: 'coin', asset: '/static/assets/eye-styles/coin.svg', socketless: true, names: Object.freeze({ zh: '金币', en: 'Coin', fr: 'Pièce', ja: 'コイン' }) }),
    Object.freeze({ id: 'dizzy', asset: '/static/assets/eye-styles/dizzy.svg', socketless: true, names: Object.freeze({ zh: '眩晕', en: 'Dizzy', fr: 'Vertige', ja: 'めまい' }) }),
  ]);
  const byId = new Map(definitions.map(item => [item.id, item]));
  /* 原眼睛 10%×20%、眼白 84%×54%，视线参数 38%×56% 的等效全头像位移。 */
  const lookOffset = Object.freeze({ x: 3.192, y: 6.048 });

  function normalize(value) {
    const id = String(value || '').trim().toLowerCase();
    return byId.has(id) ? id : 'oval';
  }
  function get(value) { return byId.get(normalize(value)) || null; }
  function url(value) { return get(value)?.asset || ''; }
  function render(value) {
    const definition = get(value);
    if (!definition) return '';
    if (definition.socketAsset && definition.whiteAsset) {
      return `<img class="skin-eye-art skin-eye-art-socket" src="${definition.socketAsset}" alt="" aria-hidden="true" draggable="false"><img class="skin-eye-art skin-eye-art-white" src="${definition.whiteAsset}" alt="" aria-hidden="true" draggable="false" style="--skin-eye-socket-image:url('${definition.socketAsset}')">`;
    }
    return `<img class="skin-eye-art skin-eye-art-free" src="${definition.asset}" alt="" aria-hidden="true" draggable="false">`;
  }

  window.GTNEyeStyles = Object.freeze({ definitions, lookOffset, normalize, get, url, render });
})();
