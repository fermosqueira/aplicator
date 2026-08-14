// Service worker: el unico que habla con el servidor local.
//
// El fetch va desde aca y no desde el content script a proposito. Con host_permissions
// declarados, los pedidos del service worker no pasan por CORS ni por la CSP de LinkedIn,
// que es donde se traba el 90% de las extensiones que intentan esto.

const SERVIDOR = "http://127.0.0.1:8765";

// El token vive en token.js, que no se versiona: un secreto hardcodeado en un repo
// publico es una mala idea aunque el chequeo de Origin ya bloquee a las paginas ajenas.
let TOKEN = null;
try {
  importScripts("token.js");
  TOKEN = self.APLICADOR_TOKEN || null;
} catch (e) {
  TOKEN = null; // falta el archivo: lo avisamos abajo, con una salida clara
}
if (TOKEN && TOKEN.startsWith("PEGA_ACA")) TOKEN = null;

chrome.runtime.onMessage.addListener((mensaje, _emisor, responder) => {
  consultar(mensaje).then(responder);
  return true; // mantiene vivo el canal: la respuesta es asincronica
});

// Click en el icono de la barra: abre el historial. Si ya hay una pestaña con el panel,
// la reutiliza en vez de acumular copias.
chrome.action.onClicked.addListener(async () => {
  const url = `${SERVIDOR}/historial`;
  const abiertas = await chrome.tabs.query({ url: `${SERVIDOR}/*` });
  if (abiertas.length) {
    await chrome.tabs.update(abiertas[0].id, { active: true, url });
    await chrome.windows.update(abiertas[0].windowId, { focused: true });
  } else {
    await chrome.tabs.create({ url });
  }
});

async function consultar({ ruta, datos }) {
  if (!TOKEN) return { ok: false, error: "falta_token" };
  try {
    const respuesta = await fetch(SERVIDOR + ruta, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Aplicador-Token": TOKEN,
      },
      body: JSON.stringify(datos || {}),
    });

    const cuerpo = await respuesta.json().catch(() => ({}));
    if (!respuesta.ok) {
      return { ok: false, error: cuerpo.error || `El servidor respondio ${respuesta.status}` };
    }
    return cuerpo;
  } catch (e) {
    // Distinguimos este caso porque tiene una solucion concreta que mostrarle al usuario:
    // levantar iniciar.bat. No es lo mismo que un error del servidor.
    return { ok: false, error: "servidor_caido" };
  }
}
