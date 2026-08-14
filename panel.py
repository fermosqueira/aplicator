"""La pagina del historial.

Se sirve desde el propio servidor local, asi que los pedidos que hace son same-origin: no
hay preflight ni CORS, y el token puede venir embebido porque la pagina la generamos aca.

Todo va en un solo archivo, sin CDN, por el mismo criterio que el resto del proyecto: nada
de esto tiene que depender de que haya internet ni de que un tercero siga publicando algo.
"""

from __future__ import annotations

PAGINA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aplicador · historial</title>
<style>
  :root {
    --fondo: #f4f2ee; --tarjeta: #fff; --texto: #1d2226; --suave: #5f6468;
    --borde: #e0dfdc; --azul: #0a66c2; --verde: #1d5c30; --verde-fondo: #e9f5ec;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --fondo: #1b1f23; --tarjeta: #22272b; --texto: #e8e6e3; --suave: #9aa0a6;
      --borde: #363c42; --azul: #6cb1f5; --verde: #a5d3b2; --verde-fondo: #23342a;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px; background: var(--fondo); color: var(--texto);
    font-family: -apple-system, "Segoe UI", Roboto, sans-serif; font-size: 14px;
  }
  .caja { max-width: 1000px; margin: 0 auto; }
  header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 4px; }
  h1 { font-size: 20px; margin: 0; }
  .estado { font-size: 12px; color: var(--suave); }
  .punto { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #2ea043; }

  .controles { display: flex; gap: 8px; margin: 16px 0; }
  input[type=search] {
    flex: 1; padding: 10px 12px; font-size: 14px; border-radius: 6px;
    border: 1px solid var(--borde); background: var(--tarjeta); color: var(--texto);
  }
  input[type=search]:focus { outline: 2px solid var(--azul); outline-offset: -1px; }
  button {
    padding: 10px 16px; font-size: 14px; font-weight: 600; border-radius: 6px;
    border: 1px solid var(--borde); background: var(--tarjeta); color: var(--texto);
    cursor: pointer; white-space: nowrap;
  }
  button:hover:not(:disabled) { border-color: var(--azul); color: var(--azul); }
  button:disabled { opacity: .55; cursor: default; }

  .resumen { font-size: 12px; color: var(--suave); margin-bottom: 10px; }

  .fila {
    background: var(--tarjeta); border: 1px solid var(--borde); border-radius: 8px;
    margin-bottom: 8px; overflow: hidden;
  }
  .cabecera { display: grid; grid-template-columns: 92px 1fr 1fr 120px; gap: 12px;
    padding: 12px 14px; cursor: pointer; align-items: center; }
  .cabecera:hover { background: rgba(127,127,127,.06); }
  .fecha { font-size: 12px; color: var(--suave); }
  .empresa { font-weight: 600; }
  .puesto { color: var(--suave); }
  .marca-si { color: var(--verde); background: var(--verde-fondo); border-radius: 10px;
    padding: 2px 8px; font-size: 11px; font-weight: 600; text-align: center; }
  .marca-no { color: var(--suave); font-size: 11px; text-align: center; }

  .detalle { display: none; padding: 0 14px 14px; border-top: 1px solid var(--borde); }
  .fila.abierta .detalle { display: block; }
  .dato { margin-top: 10px; font-size: 12px; color: var(--suave); }
  .dato b { color: var(--texto); font-weight: 600; }
  .post {
    margin-top: 10px; padding: 12px; background: var(--fondo); border-radius: 6px;
    white-space: pre-wrap; line-height: 1.5; max-height: 340px; overflow-y: auto;
  }
  .enlaces { margin-top: 10px; display: flex; gap: 14px; flex-wrap: wrap; }
  a { color: var(--azul); }
  .vacio { text-align: center; color: var(--suave); padding: 40px 0; }
</style>
</head>
<body>
<div class="caja">
  <header>
    <h1>Postulaciones</h1>
    <span class="estado"><span class="punto"></span> servidor activo desde __ARRANQUE__</span>
  </header>

  <div class="controles">
    <input type="search" id="q" placeholder="Buscar por empresa, puesto, mail o cualquier palabra del post…" autofocus>
    <button id="respuestas">Buscar respuestas</button>
  </div>

  <div class="resumen" id="resumen">Cargando…</div>
  <div id="listado"></div>
</div>

<script>
const TOKEN = "__TOKEN__";

async function pedir(ruta, datos) {
  const r = await fetch(ruta, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Aplicador-Token": TOKEN },
    body: JSON.stringify(datos || {}),
  });
  return r.json();
}

const esc = (t) => { const d = document.createElement("div"); d.textContent = t ?? ""; return d.innerHTML; };

function pintar(filas) {
  const listado = document.getElementById("listado");
  const resumen = document.getElementById("resumen");

  if (!filas.length) {
    listado.innerHTML = '<div class="vacio">No hay postulaciones que coincidan.</div>';
    resumen.textContent = "";
    return;
  }

  const respondidas = filas.filter((f) => f.respondida).length;
  resumen.textContent = `${filas.length} postulación${filas.length === 1 ? "" : "es"} · ${respondidas} respondida${respondidas === 1 ? "" : "s"}`;

  listado.innerHTML = filas.map((f) => `
    <div class="fila">
      <div class="cabecera">
        <span class="fecha">${esc(f.enviada_en.slice(0, 10))}</span>
        <span class="empresa">${esc(f.empresa || "—")}</span>
        <span class="puesto">${esc(f.puesto || "—")}</span>
        <span class="${f.respondida ? "marca-si" : "marca-no"}">${f.respondida ? "respondida" : "sin respuesta"}</span>
      </div>
      <div class="detalle">
        <div class="dato"><b>${esc(f.email)}</b>${f.recruiter ? " · " + esc(f.recruiter) : ""}</div>
        ${f.autor_post ? `<div class="dato">Publicado por <b>${esc(f.autor_post)}</b></div>` : ""}
        ${f.respondida_en ? `<div class="dato">Respondieron el <b>${esc(f.respondida_en.slice(0, 10))}</b></div>` : ""}
        ${f.texto_post ? `<div class="post">${esc(f.texto_post)}</div>` : '<div class="dato">Sin el texto del post: es anterior a que se empezara a guardar.</div>'}
        <div class="enlaces">
          ${f.url_post ? `<a href="${esc(f.url_post)}" target="_blank" rel="noopener">Ver la publicación</a>` : ""}
          ${f.hilo ? `<a href="https://mail.google.com/mail/u/0/#all/${esc(f.hilo)}" target="_blank" rel="noopener">Abrir el hilo en Gmail</a>` : ""}
        </div>
      </div>
    </div>`).join("");

  listado.querySelectorAll(".cabecera").forEach((c) =>
    c.addEventListener("click", () => c.parentElement.classList.toggle("abierta"))
  );
}

let pendiente = null;
async function buscar() {
  const datos = await pedir("/buscar", { q: document.getElementById("q").value });
  if (datos.ok) pintar(datos.filas);
}

document.getElementById("q").addEventListener("input", () => {
  clearTimeout(pendiente);
  pendiente = setTimeout(buscar, 200);
});

document.getElementById("respuestas").addEventListener("click", async (e) => {
  const boton = e.target;
  boton.disabled = true;
  boton.textContent = "Revisando Gmail…";
  const r = await pedir("/respuestas", {});
  boton.disabled = false;
  boton.textContent = "Buscar respuestas";
  if (!r.ok) {
    document.getElementById("resumen").textContent = "Error: " + (r.error || "desconocido");
    return;
  }
  await buscar();
  if (r.nuevas.length) {
    document.getElementById("resumen").textContent =
      `${r.nuevas.length} respuesta${r.nuevas.length === 1 ? "" : "s"} nueva${r.nuevas.length === 1 ? "" : "s"}: ` +
      r.nuevas.map((n) => `${n.empresa || n.email}`).join(", ");
  }
});

buscar();
</script>
</body>
</html>
"""


def render(token: str, arranque: str) -> bytes:
    return PAGINA.replace("__TOKEN__", token).replace("__ARRANQUE__", arranque).encode("utf-8")
