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
    --rojo: #8a1c1c; --rojo-fondo: #fbeaea;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --fondo: #1b1f23; --tarjeta: #22272b; --texto: #e8e6e3; --suave: #9aa0a6;
      --borde: #363c42; --azul: #6cb1f5; --verde: #a5d3b2; --verde-fondo: #23342a;
      --rojo: #f0a5a5; --rojo-fondo: #3a2424;
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
  .marca-rebote { color: var(--rojo); background: var(--rojo-fondo); border-radius: 10px;
    padding: 2px 8px; font-size: 11px; font-weight: 600; text-align: center; }
  .aviso-rebote { margin-top: 10px; padding: 10px 12px; border-radius: 6px;
    background: var(--rojo-fondo); color: var(--rojo); font-size: 12px; }
  .marca-descartada { color: var(--rojo); background: var(--rojo-fondo); border-radius: 10px;
    padding: 2px 8px; font-size: 11px; font-weight: 600; text-align: center; }

  /* Descartada: el renglón queda tachado y apagado, pero legible. Es historial, no basura:
     dentro de tres meses sirve saber que a esta empresa ya le escribiste. */
  .fila.descartada .empresa, .fila.descartada .puesto, .fila.descartada .fecha {
    text-decoration: line-through; opacity: .6;
  }
  .fila.descartada { border-color: var(--rojo); }
  .acciones { margin-top: 12px; display: flex; gap: 8px; }
  .acciones button { padding: 6px 12px; font-size: 12px; }
  .acciones .descartar:hover:not(:disabled) { border-color: var(--rojo); color: var(--rojo); }

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
    <span class="estado" id="estado"><span class="punto"></span> servidor activo desde __ARRANQUE__</span>
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

// Tres estados, no dos. Un rebote no es una respuesta: el mail nunca llegó a nadie. Dice
// "error" y no "respondida" justamente para que la oferta no quede dada por cerrada.
function estadoDe(f) {
  if (f.rebotada) return { clase: "marca-rebote", texto: "error" };
  // Descartada gana sobre respondida: la respuesta fue el "no", y eso es lo que importa.
  if (f.descartada) return { clase: "marca-descartada", texto: "descartada" };
  if (f.respondida) return { clase: "marca-si", texto: "respondida" };
  return { clase: "marca-no", texto: "sin respuesta" };
}

function pintar(filas) {
  const listado = document.getElementById("listado");
  const resumen = document.getElementById("resumen");

  if (!filas.length) {
    listado.innerHTML = '<div class="vacio">No hay postulaciones que coincidan.</div>';
    resumen.textContent = "";
    return;
  }

  const respondidas = filas.filter((f) => f.respondida && !f.descartada).length;
  const descartadas = filas.filter((f) => f.descartada).length;
  const conError = filas.filter((f) => f.rebotada).length;
  // "postulación" pierde el acento en plural: no alcanza con pegarle "es" atrás.
  resumen.textContent =
    `${filas.length} ${filas.length === 1 ? "postulación" : "postulaciones"} · ` +
    `${respondidas} respondida${respondidas === 1 ? "" : "s"}` +
    (descartadas ? ` · ${descartadas} descartada${descartadas === 1 ? "" : "s"}` : "") +
    (conError ? ` · ${conError} con error, sin enviar` : "");

  listado.innerHTML = filas.map((f) => {
    const estado = estadoDe(f);
    return `
    <div class="fila${f.descartada ? " descartada" : ""}" data-id="${f.id}">
      <div class="cabecera">
        <span class="fecha">${esc(f.enviada_en.slice(0, 10))}</span>
        <span class="empresa">${esc(f.empresa || "—")}</span>
        <span class="puesto">${esc(f.puesto || "—")}</span>
        <span class="${estado.clase}">${estado.texto}</span>
      </div>
      <div class="detalle">
        <div class="dato"><b>${esc(f.email)}</b>${f.recruiter ? " · " + esc(f.recruiter) : ""}</div>
        ${f.autor_post ? `<div class="dato">Publicado por <b>${esc(f.autor_post)}</b></div>` : ""}
        ${f.rebotada ? `<div class="aviso-rebote">
            <b>El mail no llegó.</b> Rebotó el ${esc((f.rebotada_en || "").slice(0, 10))}, así que esta postulación no está hecha.
            ${f.sugerencia_dominio ? `La dirección termina en <b>@${esc(f.email.split("@")[1] || "")}</b> y se parece a <b>@${esc(f.sugerencia_dominio)}</b>: probablemente sea un typo.` : "Revisá la publicación y confirmá la dirección."}
          </div>` : ""}
        ${f.respondida_en ? `<div class="dato">Respondieron el <b>${esc(f.respondida_en.slice(0, 10))}</b></div>` : ""}
        ${f.texto_post ? `<div class="post">${esc(f.texto_post)}</div>` : '<div class="dato">Sin el texto del post: es anterior a que se empezara a guardar.</div>'}
        <div class="enlaces">
          ${f.url_post ? `<a href="${esc(f.url_post)}" target="_blank" rel="noopener">Ver la publicación</a>` : ""}
          ${f.hilo ? `<a href="https://mail.google.com/mail/u/0/#all/${esc(f.hilo)}" target="_blank" rel="noopener">Abrir el hilo en Gmail</a>` : ""}
        </div>
        <div class="acciones">
          <button class="descartar" data-id="${f.id}" data-valor="${f.descartada ? "0" : "1"}">
            ${f.descartada ? "↩️ Volver a activas" : "👎 (no te rindas)"}
          </button>
          ${f.descartada_en ? `<span class="dato" style="margin:0;align-self:center">descartada el ${esc(f.descartada_en.slice(0, 10))}</span>` : ""}
        </div>
      </div>
    </div>`;
  }).join("");

  listado.querySelectorAll(".cabecera").forEach((c) =>
    c.addEventListener("click", () => c.parentElement.classList.toggle("abierta"))
  );

  listado.querySelectorAll(".descartar").forEach((b) =>
    b.addEventListener("click", async (e) => {
      e.stopPropagation(); // si no, se cierra la fila de golpe
      b.disabled = true;
      const r = await pedir("/descartar", {
        id: Number(b.dataset.id),
        descartada: b.dataset.valor === "1",
      });
      if (!r.ok) {
        b.disabled = false;
        document.getElementById("resumen").textContent = "Error: " + (r.error || "desconocido");
        return;
      }
      // Se vuelve a pedir la lista en vez de tocar el DOM a mano: así lo que se ve es lo
      // que quedó guardado, y no una suposición sobre lo que se guardó.
      const abiertas = [...listado.querySelectorAll(".fila.abierta")].map((f) => f.dataset.id);
      await buscar();
      abiertas.forEach((id) => listado.querySelector(`.fila[data-id="${id}"]`)?.classList.add("abierta"));
    })
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
  await estado();

  const partes = [];
  if (r.nuevas.length) {
    partes.push(`${r.nuevas.length} respuesta${r.nuevas.length === 1 ? "" : "s"}: ` +
      r.nuevas.map((n) => n.empresa || n.email).join(", "));
  }
  if ((r.rebotes || []).length) {
    partes.push(`${r.rebotes.length} con error (el mail no llegó): ` +
      r.rebotes.map((n) => n.email).join(", "));
  }
  if (partes.length) document.getElementById("resumen").textContent = partes.join(" · ");
});

// El revisor corre solo cada media hora. Mostrar cuándo fue la última pasada es lo que
// diferencia "no te contestó nadie" de "hace rato que no mira".
async function estado() {
  try {
    const r = await (await fetch("/ping")).json();
    const cuando = r.ultima_revision
      ? `última revisión ${r.ultima_revision} (${r.resultado_revision})`
      : "primera revisión en unos minutos";
    document.getElementById("estado").innerHTML =
      `<span class="punto"></span> activo desde ${esc(r.desde)} · ${esc(cuando)}`;
  } catch (e) { /* si el servidor no responde, queda el texto del arranque */ }
}

buscar();
estado();
</script>
</body>
</html>
"""


def render(token: str, arranque: str) -> bytes:
    return PAGINA.replace("__TOKEN__", token).replace("__ARRANQUE__", arranque).encode("utf-8")
