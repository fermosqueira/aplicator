// El panel que se abre al clickear un mail.
//
// Es un drawer pegado a la derecha y NO un modal: no hay backdrop, la pagina sigue
// clickeable y scrolleable detras. Completar estos campos exige leer el post, asi que
// taparlo seria pedirle al usuario que memorice. Por lo mismo el texto de la publicacion
// viaja adentro del panel: el mail suele ser de una consultora y el dato real de que
// empresa y que puesto es solo esta en el cuerpo del post.
//
// Vive dentro de un Shadow DOM: LinkedIn tiene cientos de reglas CSS globales y sin esa
// barrera el formulario se deforma solo. Por el mismo motivo los estilos van aca adentro
// como texto y no en un .css aparte.

(() => {
  const ESTILOS = `
    :host { all: initial; }
    * { box-sizing: border-box; font-family: -apple-system, "Segoe UI", Roboto, sans-serif; }

    .panel {
      position: fixed; top: 0; right: 0; bottom: 0; z-index: 2147483647;
      width: 400px; max-width: 100vw;
      background: #fff; color: #1d2226;
      box-shadow: -4px 0 26px rgba(0, 0, 0, .18);
      display: flex; flex-direction: column;
      animation: entrar .18s ease-out;
    }
    @keyframes entrar {
      from { transform: translateX(30px); opacity: 0 }
      to   { transform: none; opacity: 1 }
    }
    /* En pantallas angostas el feed se corre a la derecha y el drawer empieza a pisarlo.
       Achicarlo no lo evita del todo, pero deja mas post a la vista. Que igual se pueda
       leer en esos casos es justamente para lo que el post viaja adentro del panel. */
    @media (max-width: 1200px) { .panel { width: 340px; } }

    .encabezado {
      padding: 14px 18px 12px; border-bottom: 1px solid #e0dfdc;
      display: flex; align-items: flex-start; gap: 10px; flex: none;
    }
    .encabezado h2 { margin: 0; font-size: 16px; font-weight: 600; flex: 1; }
    .destino { margin: 2px 0 0; font-size: 12.5px; color: #0a66c2; word-break: break-all; }
    .cerrar {
      border: none; background: transparent; cursor: pointer; font-size: 20px;
      line-height: 1; color: #5f6468; padding: 2px 4px; border-radius: 4px;
    }
    .cerrar:hover { background: #efefef; color: #1d2226; }

    .contenido { flex: 1; overflow-y: auto; padding: 4px 18px 18px; }

    details.post {
      margin: 14px 0 4px; background: #f4f2ee; border-radius: 6px; padding: 9px 11px;
      font-size: 12.5px;
    }
    details.post summary {
      cursor: pointer; font-weight: 600; color: #46494d; list-style: none;
      display: flex; align-items: center; gap: 6px;
    }
    details.post summary::-webkit-details-marker { display: none; }
    details.post summary::before { content: "▸"; font-size: 10px; }
    details.post[open] summary::before { content: "▾"; }
    .post .texto {
      margin-top: 8px; max-height: 190px; overflow-y: auto;
      white-space: pre-wrap; line-height: 1.45; color: #46494d;
    }

    label { display: block; font-size: 12px; font-weight: 600; margin: 13px 0 4px; color: #46494d; }
    label .suave { font-weight: 400; color: #767b80; }
    input[type=text] {
      width: 100%; padding: 8px 10px; font-size: 14px; color: #1d2226;
      border: 1px solid #b0b6bb; border-radius: 5px; background: #fff;
    }
    input[type=text]:focus { outline: 2px solid #0a66c2; outline-offset: -1px; border-color: #0a66c2; }

    .sugerencia {
      margin-top: 5px; font-size: 12px; color: #5f6468;
      display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
    }
    .sugerencia button {
      border: 1px solid #0a66c2; background: #fff; color: #0a66c2; cursor: pointer;
      font-size: 11.5px; font-weight: 600; padding: 2px 9px; border-radius: 11px;
    }
    .sugerencia button:hover { background: #eaf3fc; }

    .idiomas { display: flex; gap: 8px; margin-top: 4px; }
    .idiomas button {
      flex: 1; padding: 8px; font-size: 13px; cursor: pointer; background: #fff;
      border: 1px solid #b0b6bb; border-radius: 5px; color: #46494d;
    }
    .idiomas button[aria-pressed="true"] {
      background: #eaf3fc; border-color: #0a66c2; color: #0a66c2; font-weight: 600;
    }

    .aviso { margin-top: 13px; padding: 9px 11px; border-radius: 6px; font-size: 12.5px; line-height: 1.45; }
    .aviso.repetido { background: #fdf3e2; border: 1px solid #e8c88a; color: #6b4c11; }
    .aviso.error    { background: #fdecea; border: 1px solid #f0b3ad; color: #7d2318; }
    .aviso.ok       { background: #e9f5ec; border: 1px solid #a5d3b2; color: #1d5c30; }
    .aviso code { background: rgba(0,0,0,.06); padding: 1px 5px; border-radius: 3px; font-size: 11.5px; }

    .previo {
      margin-top: 13px; padding: 11px; background: #f4f2ee; border-radius: 6px;
      font-size: 12.5px; line-height: 1.5; white-space: pre-wrap; word-break: break-word;
    }
    .previo .cabecera { font-weight: 600; margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid #dcd9d3; }

    .pie { flex: none; padding: 12px 18px; border-top: 1px solid #e0dfdc; display: flex; gap: 8px; }
    .pie button { padding: 9px 16px; font-size: 14px; font-weight: 600; border-radius: 20px; cursor: pointer; }
    .primario   { background: #0a66c2; color: #fff; border: none; flex: 1; }
    .primario:hover:not(:disabled) { background: #08508f; }
    .secundario { background: #fff; color: #46494d; border: 1px solid #8f979e; }
    button:disabled { opacity: .55; cursor: default; }
  `;

  const TEXTO = {
    servidor_caido:
      "No encuentro el servidor local. Abrí <code>iniciar.bat</code> en la carpeta Aplicador y volvé a intentar.",
    falta_token:
      "Falta <code>extension/token.js</code>. Copiá <code>token.example.js</code> con ese nombre y pegale el mismo token que está en <code>config.json</code>.",
  };

  function pedir(ruta, datos) {
    return new Promise((resolver) => {
      try {
        chrome.runtime.sendMessage({ ruta, datos }, (respuesta) => {
          if (chrome.runtime.lastError) {
            resolver({ ok: false, error: "La extension se recargo. Actualizá la pagina (F5)." });
          } else {
            resolver(respuesta || { ok: false, error: "Sin respuesta del servidor." });
          }
        });
      } catch (e) {
        resolver({ ok: false, error: "La extension se recargo. Actualizá la pagina (F5)." });
      }
    });
  }

  function abrir({ email, texto, autor, url, chip }) {
    cerrarAbierto();

    const anfitrion = document.createElement("aplicador-modal");
    const raiz = anfitrion.attachShadow({ mode: "open" });
    document.body.appendChild(anfitrion);
    chip?.classList.add("aplicador-chip--activo");

    raiz.innerHTML = `
      <style>${ESTILOS}</style>
      <aside class="panel" role="dialog" aria-label="Postularse">
        <div class="encabezado">
          <div style="flex:1">
            <h2>Postularse</h2>
            <p class="destino">${escapar(email)}</p>
          </div>
          <button class="cerrar" id="cerrar" title="Cerrar (Esc)" aria-label="Cerrar">×</button>
        </div>

        <div class="contenido">
          ${texto ? `
            <details class="post" open>
              <summary>Publicación</summary>
              <div class="texto">${escapar(texto)}</div>
            </details>` : ""}

          <label for="empresa">Empresa</label>
          <input type="text" id="empresa" autocomplete="off">
          <div class="sugerencia" id="sug-autor" hidden></div>

          <label for="puesto">Puesto</label>
          <input type="text" id="puesto" autocomplete="off">

          <label for="recruiter">Nombre de quien recibe <span class="suave">(opcional)</span></label>
          <input type="text" id="recruiter" autocomplete="off" placeholder="Ana">

          <label>Idioma</label>
          <div class="idiomas">
            <button type="button" data-idioma="es" aria-pressed="true">Español</button>
            <button type="button" data-idioma="en" aria-pressed="false">English</button>
          </div>

          <div id="mensajes"></div>
        </div>

        <div class="pie">
          <button type="button" class="secundario" id="cancelar">Cancelar</button>
          <button type="button" class="primario" id="principal" disabled>Cargando…</button>
        </div>
      </aside>
    `;

    const $ = (sel) => raiz.querySelector(sel);
    const campos = { empresa: $("#empresa"), puesto: $("#puesto"), recruiter: $("#recruiter") };
    const mensajes = $("#mensajes");
    const principal = $("#principal");
    const contenido = $(".contenido");

    let idioma = "es";
    let confirmado = false; // en el segundo click ya vio el borrador
    let enviando = false;

    const cerrar = () => {
      if (enviando) return;
      chip?.classList.remove("aplicador-chip--activo");
      anfitrion.remove();
      document.removeEventListener("keydown", alTeclear, true);
    };

    const alTeclear = (e) => {
      if (e.key === "Escape" && !enviando) {
        e.stopPropagation();
        cerrar();
      }
    };

    const avisar = (tipo, html) => {
      mensajes.querySelectorAll(`.aviso.${tipo}`).forEach((n) => n.remove());
      const div = document.createElement("div");
      div.className = `aviso ${tipo}`;
      div.innerHTML = html;
      mensajes.appendChild(div);
      contenido.scrollTop = contenido.scrollHeight;
    };

    const datosActuales = () => ({
      email,
      empresa: campos.empresa.value.trim(),
      puesto: campos.puesto.value.trim(),
      recruiter: campos.recruiter.value.trim(),
      idioma,
      // El post viaja con el envio y queda guardado: es lo que despues permite saber a que
      // oferta correspondia una respuesta, cuando el titulo del puesto ya no alcanza.
      texto: texto || "",
      autor: autor || "",
      url: url || "",
    });

    const invalidarBorrador = () => {
      if (!confirmado) return;
      confirmado = false;
      principal.textContent = "Ver borrador";
      mensajes.querySelector(".previo")?.remove();
    };

    // Cualquier edicion invalida el borrador ya mostrado: hay que volver a mirarlo.
    Object.values(campos).forEach((campo) =>
      campo.addEventListener("input", invalidarBorrador)
    );

    raiz.querySelectorAll(".idiomas button").forEach((boton) =>
      boton.addEventListener("click", () => {
        idioma = boton.dataset.idioma;
        raiz.querySelectorAll(".idiomas button").forEach((b) =>
          b.setAttribute("aria-pressed", String(b === boton))
        );
        invalidarBorrador();
      })
    );

    $("#cerrar").addEventListener("click", cerrar);
    $("#cancelar").addEventListener("click", cerrar);

    // LinkedIn tiene atajos de una sola tecla; sin esto, escribir en el form los dispara.
    raiz.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Escape") cerrar();
      if (e.key === "Enter" && e.target.tagName === "INPUT" && !principal.disabled) {
        principal.click();
      }
    });
    // Sin backdrop no hay donde clickear afuera, asi que Escape se escucha global.
    document.addEventListener("keydown", alTeclear, true);

    principal.addEventListener("click", async () => {
      if (!confirmado) {
        principal.disabled = true;
        principal.textContent = "Armando…";
        const vista = await pedir("/previsualizar", datosActuales());
        principal.disabled = false;

        if (!vista.ok) {
          principal.textContent = "Ver borrador";
          avisar("error", TEXTO[vista.error] || escapar(vista.error));
          return;
        }

        mensajes.querySelector(".previo")?.remove();
        const previo = document.createElement("div");
        previo.className = "previo";
        previo.innerHTML =
          `<div class="cabecera">${escapar(vista.asunto)}\nAdjunto: ${escapar(vista.cv)} · Etiqueta: ${escapar(vista.etiqueta)}</div>` +
          escapar(vista.cuerpo);
        mensajes.appendChild(previo);
        contenido.scrollTop = contenido.scrollHeight;

        confirmado = true;
        principal.textContent = "Enviar ahora";
        return;
      }

      enviando = true;
      principal.disabled = true;
      principal.textContent = "Enviando…";

      const resultado = await pedir("/enviar", datosActuales());
      enviando = false;

      if (!resultado.ok) {
        principal.disabled = false;
        principal.textContent = "Enviar ahora";
        avisar("error", TEXTO[resultado.error] || escapar(resultado.error));
        return;
      }

      mensajes.innerHTML = "";
      const etiqueta = resultado.etiquetada
        ? `Etiquetado como <code>${escapar(resultado.etiqueta)}</code>.`
        : "El mail salio, pero no se pudo aplicar la etiqueta. Quedo registrado igual.";
      avisar("ok", `Enviado a <b>${escapar(resultado.destino)}</b>. ${etiqueta}`);
      principal.textContent = "Listo";
      principal.disabled = false;
      principal.onclick = cerrar;
      setTimeout(cerrar, 4000);
    });

    // El autor del post como alternativa para Empresa: cuando el mail es de una consultora
    // externa, el dominio miente y el dato bueno es quien publico.
    const mostrarAutor = () => {
      const caja = $("#sug-autor");
      if (!autor || autor.trim().toLowerCase() === campos.empresa.value.trim().toLowerCase()) {
        caja.hidden = true;
        return;
      }
      caja.hidden = false;
      caja.innerHTML = `<span>Publicado por <b>${escapar(autor)}</b></span>`;
      const boton = document.createElement("button");
      boton.type = "button";
      boton.textContent = "usar como empresa";
      boton.addEventListener("click", () => {
        campos.empresa.value = autor;
        invalidarBorrador();
        mostrarAutor();
      });
      caja.appendChild(boton);
    };

    // Sugerencias y duplicados, mientras el usuario ya empieza a leer.
    pedir("/sugerir", { email, texto }).then((s) => {
      if (s.ok) {
        if (s.empresa) campos.empresa.value = s.empresa;
        if (s.puesto) campos.puesto.value = s.puesto;
        if (s.idioma && s.idioma !== idioma) {
          raiz.querySelector(`.idiomas button[data-idioma="${s.idioma}"]`)?.click();
        }
        if (s.duplicados?.length) {
          const previas = s.duplicados
            .map((d) => `${d.fecha} · ${d.empresa || "?"} — ${d.puesto || "?"}`)
            .join("<br>");
          avisar("repetido", `<b>Ya le escribiste a esta direccion:</b><br>${previas}`);
        }
      } else {
        avisar("error", TEXTO[s.error] || escapar(s.error));
      }

      mostrarAutor();
      principal.disabled = false;
      principal.textContent = "Ver borrador";
      (campos.empresa.value ? campos.puesto : campos.empresa).focus();
    });
  }

  function cerrarAbierto() {
    document.querySelectorAll(".aplicador-chip--activo").forEach((c) =>
      c.classList.remove("aplicador-chip--activo")
    );
    document.querySelector("aplicador-modal")?.remove();
  }

  function escapar(texto) {
    const div = document.createElement("div");
    div.textContent = texto == null ? "" : String(texto);
    return div.innerHTML;
  }

  window.AplicadorModal = { abrir };
})();
