// Los avisos flotantes de abajo a la izquierda.
//
// Vive aparte del drawer y no adentro por una razon concreta: el drawer se cierra apenas
// clickeas "Enviar ahora", asi que ya no existe cuando llega la respuesta del servidor.
// El aviso tiene que sobrevivirlo.
//
// Los content scripts comparten el mismo mundo aislado, asi que se hablan por window,
// igual que modal.js y contenido.js.

(() => {
  const ESTILOS = `
    :host { all: initial; }
    * { box-sizing: border-box; font-family: -apple-system, "Segoe UI", Roboto, sans-serif; }

    .pila {
      position: fixed; left: 20px; bottom: 20px; z-index: 2147483647;
      display: flex; flex-direction: column-reverse; gap: 8px;
      max-width: 360px; pointer-events: none;
    }

    .aviso {
      pointer-events: auto;
      padding: 11px 14px; border-radius: 8px; font-size: 13px; line-height: 1.45;
      box-shadow: 0 4px 16px rgba(0, 0, 0, .18);
      border: 1px solid transparent;
      animation: entrar .18s ease-out;
      word-break: break-word;
    }
    @keyframes entrar {
      from { transform: translateY(8px); opacity: 0 }
      to   { transform: none; opacity: 1 }
    }
    .aviso.yendose { opacity: 0; transform: translateY(8px); transition: all .25s ease-in; }

    .aviso.enviando { background: #eef3f8; border-color: #c8d4de; color: #46494d; }
    .aviso.ok       { background: #e9f5ec; border-color: #a5d3b2; color: #14522a; }
    .aviso.error    { background: #fdecea; border-color: #f0b3ad; color: #7d2318; cursor: pointer; }

    .aviso code { background: rgba(0,0,0,.07); padding: 1px 5px; border-radius: 3px; font-size: 11.5px; }
    .cerrar { display: block; margin-top: 6px; font-size: 11.5px; opacity: .75; }
  `;

  // El verde se va solo: ya cumplio. El rojo no, porque un error que desaparece antes de que
  // lo leas es un error que no paso.
  const DURACION = { ok: 4000, enviando: 0, error: 0 };

  let pila = null;

  function contenedor() {
    if (pila?.isConnected) return pila;
    const anfitrion = document.createElement("aplicador-avisos");
    const raiz = anfitrion.attachShadow({ mode: "open" });
    raiz.innerHTML = `<style>${ESTILOS}</style><div class="pila"></div>`;
    document.body.appendChild(anfitrion);
    pila = raiz.querySelector(".pila");
    return pila;
  }

  function sacar(nodo) {
    nodo.classList.add("yendose");
    setTimeout(() => nodo.remove(), 250);
  }

  function mostrar(estado, html) {
    const nodo = document.createElement("div");
    // Se apila al principio y el contenedor va en column-reverse: el mas nuevo queda abajo,
    // pegado al borde, que es donde uno mira.
    contenedor().prepend(nodo);

    let reloj = null;

    const pintar = (nuevoEstado, nuevoHtml) => {
      clearTimeout(reloj);
      nodo.className = `aviso ${nuevoEstado}`;
      nodo.innerHTML =
        nuevoHtml + (nuevoEstado === "error" ? `<span class="cerrar">clickeá para cerrar</span>` : "");
      const espera = DURACION[nuevoEstado] ?? 4000;
      if (espera) reloj = setTimeout(() => sacar(nodo), espera);
    };

    nodo.addEventListener("click", () => {
      if (nodo.classList.contains("error")) sacar(nodo);
    });

    pintar(estado, html);
    return { actualizar: pintar };
  }

  window.AplicadorAviso = { mostrar };
})();
