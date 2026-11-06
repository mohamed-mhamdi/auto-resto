const videoCanvas = byId('video-canvas');
const videoContext = videoCanvas.getContext('2d');
let readingVideo = false;

function videoAppearance(table, now) {
  if (!table) return ['État indisponible', '#9fa9be'];
  if (table.state === 'free') return ['Libre', '#35d683'];
  if (table.state === 'cleaning') return ['À nettoyer', '#ffb735'];
  if (table.state === 'served') return ['Servie', '#ffffff'];
  const age = Math.max(0, now - table.seated);
  const late = age >= 900;
  return [late ? 'Retard ' + duration(age) : 'En attente ' + duration(age), late ? '#ff4d4f' : '#b47846'];
}

function clearPreview(status, message) {
  byId('video-status').textContent = status;
  byId('video-empty').textContent = message;
  byId('video-empty').hidden = false;
  videoCanvas.hidden = true;
  byId('video-states').replaceChildren();
}

async function refreshVideo() {
  if (byId('video').hidden || readingVideo) return;
  readingVideo = true;
  try {
    const [packet, room] = await Promise.all([request('/api/video'), request('/api/snapshot')]);
    if (!packet.online) {
      clearPreview('Aperçu hors ligne', 'Démarrez le worker avec --preview. En démo, utilisez le lanceur de replay.');
      return;
    }
    const image = new Image();
    image.src = 'data:image/jpeg;base64,' + packet.jpeg;
    await image.decode();
    if (byId('video').hidden) return;
    videoCanvas.width = image.naturalWidth;
    videoCanvas.height = image.naturalHeight;
    videoContext.drawImage(image, 0, 0);
    const tables = new Map(room.tables.map(table => [String(table.id), table]));
    const details = [];
    for (const [id, region] of Object.entries(packet.regions)) {
      const [x, y, w, h] = region.box.map((value, index) =>
        value * (index % 2 === 0 ? videoCanvas.width : videoCanvas.height));
      const [state, color] = videoAppearance(tables.get(id), room.now);
      const detected = {empty:'vide', occupied:'occupée'}[region.detected] || 'incertaine';
      const title = 'T' + id + ' · ' + state;
      videoContext.fillStyle = color + '36';
      videoContext.fillRect(x, y, w, h);
      videoContext.strokeStyle = color;
      videoContext.lineWidth = 3;
      videoContext.strokeRect(x, y, w, h);
      videoContext.font = 'bold 15px sans-serif';
      const tagWidth = Math.min(videoCanvas.width, videoContext.measureText(title).width + 12);
      const tagX = Math.min(x, videoCanvas.width - tagWidth);
      const tagY = Math.max(0, y - 24);
      videoContext.fillStyle = '#171928';
      videoContext.fillRect(tagX, tagY, tagWidth, 24);
      videoContext.fillStyle = color;
      videoContext.fillText(title, tagX + 6, tagY + 17, tagWidth - 12);
      details.push(node('li', 'Table ' + id + ' · ' + state + ' · IA ' + detected));
    }
    byId('video-states').replaceChildren(...details);
    byId('video-status').textContent = packet.demo ? 'Replay · états de démonstration' : 'Caméra en direct';
    byId('video-empty').hidden = true;
    videoCanvas.hidden = false;
  } catch {
    clearPreview('Aperçu indisponible', 'Vérifiez que le serveur local et le worker sont actifs.');
  } finally {
    readingVideo = false;
  }
}
window.addEventListener('hashchange', refreshVideo);
refreshVideo();
setInterval(refreshVideo, 550);
