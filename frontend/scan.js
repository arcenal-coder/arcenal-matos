import { BrowserMultiFormatReader } from '@zxing/browser';

const start = document.getElementById('start-scan');
const stop = document.getElementById('stop-scan');
const status = document.getElementById('scan-status');
const reader = new BrowserMultiFormatReader();
let controls;
function openResult(text) {
  try {
    const url = new URL(text);
    if (url.origin === location.origin && /^\/assets\/[0-9a-f-]+\/$/i.test(url.pathname)) {
      location.assign(url.pathname);
      return;
    }
  } catch { /* A barcode normally contains a plain asset identifier. */ }
  location.assign('/scan/?code=' + encodeURIComponent(text));
}
document.getElementById('scan-image').addEventListener('change', async event => {
  const file = event.target.files[0];
  if (!file) return;
  const imageUrl = URL.createObjectURL(file);
  try {
    openResult((await reader.decodeFromImageUrl(imageUrl)).getText());
  } catch {
    status.textContent = 'Étiquette non reconnue : essayez une photo plus nette ou saisissez l’identifiant.';
  } finally { URL.revokeObjectURL(imageUrl); }
});
stop.addEventListener('click', () => { controls?.stop(); stop.hidden = true; start.disabled = false; });
start.addEventListener('click', async () => {
  start.disabled = true;
  status.textContent = 'Autorisez la caméra puis présentez une étiquette.';
  try {
    controls = await reader.decodeFromVideoDevice(undefined, 'scan-video', (result, error, handle) => {
      if (!result) return;
      handle.stop();
      openResult(result.getText());
    });
    stop.hidden = false;
  } catch (error) {
    status.textContent = 'Caméra indisponible : utilisez HTTPS, autorisez la caméra ou saisissez l’identifiant.';
    start.disabled = false;
  }
});
