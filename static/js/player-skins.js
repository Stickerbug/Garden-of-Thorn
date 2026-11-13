/* 玩家形象的共享皮肤目录。贴图在五官下方，装饰在五官上方；
   游戏、故事模式与合成小游戏共用，避免各页面款式不一致。 */
(() => {
  /* 玩家皮肤贴图版本号：换图/改 viewBox 时 bump，让浏览器的缓存失效。
     只跟玩家皮肤素材挂钩，不随整体静态版本每次部署变化。 */
  const PLAYER_SKIN_ART_REVISION = 1;

  function withArtRevision(url) {
    if (!url || url.startsWith('data:')) return url || '';
    return `${url}${url.includes('?') ? '&' : '?'}v=${PLAYER_SKIN_ART_REVISION}`;
  }

  const ART = Object.freeze({
    circle: '<circle cx="141.73" cy="141.73" r="131.81" fill="__FILL__" stroke="__STROKE__" stroke-width="20"/>',
    ghost: '<circle cx="141.73" cy="141.73" r="131.81" fill="__FILL__" fill-opacity=".1" stroke="__STROKE__" stroke-opacity=".1" stroke-width="20"/>',
    brainDamage: '<path d="M268.64 148.08c-1.02 9.51-.41 18.51-2.43 26.36-7.32 28.45-18.11 41.86-37.05 71.18-10.1 15.64-41.19 11.17-76.57 18.96-26.39 5.81-33.58-6.33-68.3-31.09C24.25 190.67-12.87 123.42 27.14 91.66c21.86-17.35 34.71-33.2 45.25-44.94 17.92-19.95 10.04-25.57 36-30.84 9.94-2.01 37.39 6.37 62.81 14.32 47.82 14.94 89.27 31.31 97.87 57.03 7.79 23.31 1.97 38.42-.44 60.85Z" fill="__FILL__" stroke="__STROKE__" stroke-width="20" stroke-miterlimit="10"/>',
  });
  const definitions = [
    {
      id: 'classic',
      names: { zh: '经典', en: 'Classic', fr: 'Classique', ja: 'クラシック' },
      texture: '',
      decoration: '',
    },
    {
      id: 'faceless',
      names: { zh: '无脸', en: 'Faceless', fr: 'Sans visage', ja: '無顔' },
      texture: '/static/assets/player-avatars/faceless-body.svg',
      art: ART.circle,
      decoration: '',
      bodyArt: true,
      hideEyes: true,
      lookRotateOffset: 90,
      hideMouth: true,
    },
    {
      id: 'ghost',
      names: { zh: '幽灵', en: 'Ghost', fr: 'Fantôme', ja: 'ゴースト' },
      texture: '/static/assets/player-avatars/ghost-body.svg',
      art: ART.ghost,
      decoration: '',
      bodyArt: true,
    },
    {
      id: 'brain_damage',
      names: { zh: '脑损伤', en: 'Brain Damage', fr: 'Lésion cérébrale', ja: '脳損傷' },
      texture: '/static/assets/player-avatars/brain-damage-body.svg',
      art: ART.brainDamage,
      decoration: '',
      bodyArt: true,
      faceRotate: 18,
    },
    {
      id: 'corrupted',
      names: { zh: '腐化', en: 'Corrupted', fr: 'Corrompu', ja: '腐化' },
      texture: '/static/assets/player-avatars/corrupted-body.svg',
      decoration: '',
      bodyArt: true,
      fixedColor: true,
    },
    {
      id: 'mark',
      names: { zh: '标记', en: 'Mark', fr: 'Marque', ja: 'マーク' },
      texture: '/static/assets/player-avatars/mark-body.svg',
      decoration: '',
      bodyArt: true,
      fixedColor: true,
    },
    {
      id: 'nazar',
      names: { zh: '邪眼', en: 'Nazar', fr: 'Nazar', ja: 'ナザール' },
      texture: '/static/assets/player-avatars/nazar-body.svg',
      decoration: '',
      bodyArt: true,
      fixedColor: true,
      hideEyes: true,
      lookRotateOffset: 90,
      hideMouth: true,
    },
    {
      id: 'right_angle',
      names: { zh: '直角', en: 'Right Angle', fr: 'Angle droit', ja: '直角' },
      texture: '/static/assets/player-avatars/right-angle-body.svg',
      art: ART.circle,
      decoration: '',
      bodyArt: true,
      faceRotate: -90,
    },
    {
      id: 'centipede_head',
      names: { zh: '蜈蚣头', en: 'Centipede Head', fr: 'Tête de mille-pattes', ja: 'ムカデの頭' },
      texture: '/static/assets/player-avatars/centipede-head.svg',
      lookRotateOffset: 45,
      decoration: '',
      bodyArt: true,
      fixedColor: true,
      hideEyes: true,
      hideMouth: true,
      textureRotate: 90,
    },
    {
      id: 'desert_centipede_head',
      names: { zh: '沙漠蜈蚣头', en: 'Desert Centipede Head', fr: 'Tête de mille-pattes du désert', ja: '砂漠ムカデの頭' },
      texture: '/static/assets/player-avatars/desert-centipede-head.svg',
      lookRotateOffset: 45,
      decoration: '',
      bodyArt: true,
      fixedColor: true,
      hideEyes: true,
      hideMouth: true,
      textureRotate: 90,
    },
    {
      id: 'evil_centipede_head',
      names: { zh: '邪恶蜈蚣头', en: 'Evil Centipede Head', fr: 'Tête de mille-pattes maléfique', ja: '邪悪なムカデの頭' },
      texture: '/static/assets/player-avatars/evil-centipede-head.svg',
      lookRotateOffset: 45,
      decoration: '',
      bodyArt: true,
      fixedColor: true,
      hideEyes: true,
      hideMouth: true,
      textureRotate: 90,
    },
    // 赛季「塔之诅咒」角色皮肤：不进商店，由赛季/活动系统单独发放。
    {
      id: 'tower_curse_ironclad',
      names: { zh: '铁甲战士', en: 'Ironclad', fr: 'Le Ferrailleur', ja: 'アイアンクラッド' },
      texture: '/static/assets/player-avatars/tower-curse-ironclad.svg',
      decoration: '',
      bodyArt: true,
      fixedColor: true,
      hideEyes: true,
      lookRotateOffset: 90,
      hideMouth: true,
    },
    {
      id: 'tower_curse_silent',
      names: { zh: '静默猎手', en: 'Silent', fr: 'La Silencieuse', ja: 'サイレント' },
      texture: '/static/assets/player-avatars/tower-curse-silent.svg',
      decoration: '',
      bodyArt: true,
      fixedColor: true,
      hideEyes: true,
      lookRotateOffset: 90,
      hideMouth: true,
    },
    {
      id: 'tower_curse_defect',
      names: { zh: '故障机器人', en: 'Defect', fr: 'Le Défectueux', ja: 'ディフェクト' },
      texture: '/static/assets/player-avatars/tower-curse-defect.svg',
      decoration: '',
      bodyArt: true,
      fixedColor: true,
      hideEyes: true,
      lookRotateOffset: 90,
      hideMouth: true,
    },
    {
      id: 'tower_curse_necrobinder',
      names: { zh: '亡灵契约师', en: 'Necrobinder', fr: 'Le Nécrolieur', ja: 'ネクロバインダー' },
      texture: '/static/assets/player-avatars/tower-curse-necrobinder.svg',
      decoration: '',
      bodyArt: true,
      fixedColor: true,
      hideEyes: true,
      lookRotateOffset: 90,
      hideMouth: true,
    },
    {
      id: 'tower_curse_regent',
      names: { zh: '储君', en: 'Regent', fr: 'Le Régent', ja: 'リージェント' },
      texture: '/static/assets/player-avatars/tower-curse-regent.svg',
      decoration: '',
      bodyArt: true,
      fixedColor: true,
      hideEyes: true,
      lookRotateOffset: 90,
      hideMouth: true,
    },
  ].map((item) => Object.freeze({
    ...item,
    names: Object.freeze({ ...item.names }),
  }));
  const byId = new Map(definitions.map((item) => [item.id, item]));

  function normalize(value) {
    const id = String(value || '').trim().toLowerCase();
    return byId.has(id) ? id : 'classic';
  }

  function get(value) {
    return byId.get(normalize(value)) || byId.get('classic');
  }

  function normalizeColor(value, fallback) {
    const text = String(value || '').trim();
    return /^#[0-9a-fA-F]{6}$/.test(text) ? text.toUpperCase() : fallback;
  }

  function textureUrl(value, mainColor, borderColor) {
    const definition = get(value);
    if (!definition.art || definition.fixedColor) return withArtRevision(definition.texture);
    const fill = normalizeColor(mainColor, '#F2EA00');
    const stroke = normalizeColor(borderColor, '#DCDC00');
    const art = definition.art.replace(/__FILL__/g, fill).replace(/__STROKE__/g, stroke);
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 283.46 283.46">${art}</svg>`;
    return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
  }

  function renderLayers(value, options = {}) {
    const definition = get(value);
    const textureSource = textureUrl(value, options.mainColor, options.borderColor);
    const textureRotate = Number(definition.textureRotate) || 0;
    const textureStyle = textureRotate ? ` style="--skin-texture-rotate:${textureRotate}deg"` : '';
    const texture = textureSource
      ? `<img class="skin-texture-layer" src="${textureSource}" alt="" aria-hidden="true" draggable="false"${textureStyle}>`
      : '';
    const decoration = definition.decoration
      ? `<img class="skin-decoration-layer" src="${withArtRevision(definition.decoration)}" alt="" aria-hidden="true" draggable="false">`
      : '';
    return `${texture}${decoration}`;
  }

  function layerClass(value) {
    const definition = get(value);
    const classes = [];
    if (definition.texture || definition.decoration) classes.push('skin-has-layers');
    if (definition.bodyArt) classes.push('skin-has-body-art');
    if (definition.fixedColor) classes.push('skin-fixed-color');
    if (definition.hideEyes) classes.push('skin-hide-eyes');
    if (definition.hideMouth) classes.push('skin-hide-mouth');
    if (definition.id !== 'classic') classes.push(`skin-preset-${definition.id}`);
    return classes.length ? ` ${classes.join(' ')}` : '';
  }

  function faceStyle(value) {
    const rotate = Number(get(value).faceRotate);
    return Number.isFinite(rotate) && rotate ? `--skin-face-transform:rotate(${rotate}deg);` : '';
  }

  function lookRotation(look, skinValue) {
    const x = Number(look?.x);
    const y = Number(look?.y);
    if (!Number.isFinite(x) || !Number.isFinite(y) || Math.hypot(x, y) < 0.001) return 0;
    // 默认 0° 就是正右方；只有贴图本身横转 90° 的蜈蚣系列额外补 45°，
    // 让它们在默认视线（右上 45°）时正好回到正位。
    const offset = Number(get(skinValue).lookRotateOffset) || 0;
    return Math.atan2(y, x) * 180 / Math.PI + offset;
  }

  window.GTNPlayerSkins = Object.freeze({
    definitions: Object.freeze(definitions),
    normalize,
    get,
    textureUrl,
    renderLayers,
    layerClass,
    faceStyle,
    lookRotation,
  });
})();
