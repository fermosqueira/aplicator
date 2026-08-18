// Encuentra direcciones de mail en el feed de LinkedIn y las vuelve clickeables.
//
// La deteccion recorre nodos de texto con una expresion regular, no selectores CSS.
// LinkedIn renombra sus clases seguido (son generadas), asi que cualquier cosa atada a
// ".feed-shared-algo" se rompe sola en unos meses. Un mail escrito en el texto de un post,
// en cambio, siempre es un nodo de texto.

(() => {
  const MAIL = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;
  // Una copia sin /g para los chequeos: .test() sobre una regex global mueve lastIndex y
  // hace que la siguiente llamada arranque desde el medio y devuelva false de mentira.
  const MAIL_TEST = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/;
  const MARCA = "aplicador-chip";

  // Donde no tiene sentido buscar, o donde tocar el DOM romperia la pagina.
  // Los <a> quedan afuera del recorrido de texto, pero NO se ignoran: LinkedIn convierte
  // solo los mails de los posts en links mailto:, asi que son la forma mas comun en que
  // aparecen. Los maneja marcarEnlaces() aparte.
  const PROHIBIDOS = new Set([
    "A", "SCRIPT", "STYLE", "NOSCRIPT", "TEXTAREA", "INPUT", "SELECT",
    "CODE", "APLICADOR-MODAL",
  ]);

  // De mas especifico a menos. Si ninguno pega, caemos a "el ancestro con texto suficiente".
  const CONTENEDORES = [
    "div.feed-shared-update-v2",
    "div.occludable-update",
    "div[data-urn]",
    "article",
    "div.update-components-text",
  ];

  // Quien publico el post. Cuando el mail es de una consultora externa, el dominio no
  // dice nada util y este suele ser el dato que importa.
  const AUTORES = [
    ".update-components-actor__title",
    ".update-components-actor__name",
    ".feed-shared-actor__name",
    ".autor",
  ];

  function estilos() {
    if (document.getElementById("aplicador-estilos")) return;
    const style = document.createElement("style");
    style.id = "aplicador-estilos";
    style.textContent = `
      .${MARCA} {
        background: #eaf3fc !important;
        color: #0a66c2 !important;
        border-bottom: 1px dashed #0a66c2 !important;
        border-radius: 3px !important;
        padding: 0 3px !important;
        cursor: pointer !important;
      }
      .${MARCA}:hover { background: #0a66c2 !important; color: #fff !important; }
      .${MARCA}--activo {
        background: #0a66c2 !important;
        color: #fff !important;
        border-bottom-style: solid !important;
      }
      /* Ya postulado. Con el drawer cerrandose solo al enviar, esta es la unica marca
         durable en la pagina de que a esta direccion ya le escribiste. */
      .${MARCA}--enviado {
        background: #e9f5ec !important;
        color: #14522a !important;
        border-bottom-color: #1d5c30 !important;
      }
      .${MARCA}--enviado::after { content: " ✓"; font-weight: 700; }
    `;
    document.documentElement.appendChild(style);
  }

  function utilizable(nodo) {
    if (!nodo.nodeValue || nodo.nodeValue.length < 6) return false;
    for (let p = nodo.parentElement; p; p = p.parentElement) {
      if (PROHIBIDOS.has(p.tagName)) return false;
      if (p.isContentEditable) return false;
      if (p.classList?.contains(MARCA)) return false;
    }
    return true;
  }

  function completarSiQuedoCortado(nodoTexto, email, indice) {
    // LinkedIn parte el texto en varios nodos (por el "ver mas", por los resaltados). Si
    // una direccion cae justo en ese corte, la regex ve solo la primera mitad y el pedazo
    // puede seguir siendo valido: "...@gmail.co" en vez de "...@gmail.com". El mail sale,
    // rebota, y la postulacion se da por hecha. Paso de verdad una vez.
    if (indice + email.length < nodoTexto.nodeValue.length) return email; // no toca el borde

    const completo = nodoTexto.parentElement?.textContent || "";
    // Instancia propia, otra vez: .match() con una regex global le resetea el lastIndex, y
    // esta funcion se llama desde adentro del bucle de marcar().
    const candidatos = completo.match(new RegExp(MAIL.source, "g")) || [];
    const entero = candidatos.find((c) => c.startsWith(email) && c.length > email.length);
    return entero || email;
  }

  function marcar(nodoTexto) {
    const texto = nodoTexto.nodeValue;
    if (!MAIL_TEST.test(texto)) return;

    // Instancia propia por llamada. Una regex global lleva `lastIndex` mutable adentro, y
    // basta con que alguien mas la use (un .match(), un .test()) para reiniciar este bucle
    // desde cero y colgar la pestaña. Que nadie mas pueda tocar este estado es la unica
    // forma de que no vuelva a pasar.
    const buscador = new RegExp(MAIL.source, "g");
    const fragmento = document.createDocumentFragment();
    let cursor = 0;
    let m;

    while ((m = buscador.exec(texto)) !== null) {
      if (m.index > cursor) {
        fragmento.appendChild(document.createTextNode(texto.slice(cursor, m.index)));
      }
      // Copia propia por vuelta: `m` se reasigna en cada iteracion y todos los chips
      // terminarian apuntando al ultimo mail encontrado.
      const email = completarSiQuedoCortado(nodoTexto, m[0], m.index);
      const chip = document.createElement("span");
      chip.className = MARCA;
      chip.textContent = email;
      chip.title = "Postularse con el Aplicador";
      chip.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation(); // sin esto, LinkedIn abre el post
        abrirPanel(email, chip);
      });
      fragmento.appendChild(chip);
      cursor = m.index + email.length;

      // Si el email se completo, quedo mas largo que lo que matcheo la regex: hay que
      // reposicionar la busqueda para no volver a leer el pedazo que ya consumimos.
      if (cursor > buscador.lastIndex) buscador.lastIndex = cursor;
    }

    if (cursor < texto.length) {
      fragmento.appendChild(document.createTextNode(texto.slice(cursor)));
    }
    nodoTexto.parentNode?.replaceChild(fragmento, nodoTexto);
  }

  function abrirPanel(email, elemento) {
    const contenedor = contenedorDelPost(elemento);
    window.AplicadorModal.abrir({
      email,
      texto: textoDelPost(contenedor, elemento),
      autor: autorDelPost(contenedor),
      url: urlDelPost(contenedor),
      chip: elemento,
    });
  }

  function urlDelPost(contenedor) {
    // El data-urn identifica la publicacion y se puede convertir en permalink. Si el post
    // no lo trae, la URL actual sirve igual cuando ya estamos parados en el post.
    const urn = contenedor?.closest?.("[data-urn]")?.getAttribute("data-urn");
    if (urn && urn.includes("activity")) {
      return `https://www.linkedin.com/feed/update/${urn}/`;
    }
    return location.href.startsWith("https://www.linkedin.com/posts/") ? location.href : "";
  }

  function marcarEnlaces(raiz) {
    const enlaces = [];
    if (raiz.matches?.('a[href^="mailto:"]')) enlaces.push(raiz);
    if (raiz.querySelectorAll) {
      enlaces.push(...raiz.querySelectorAll('a[href^="mailto:"]'));
    }

    for (const enlace of enlaces) {
      if (enlace.dataset.aplicador) continue;
      // El href es mas confiable que el texto: LinkedIn a veces recorta lo que muestra.
      const email = decodeURIComponent(enlace.getAttribute("href").slice(7)).split("?")[0].trim();
      if (!MAIL_TEST.test(email)) continue;

      enlace.dataset.aplicador = "1";
      enlace.classList.add(MARCA);
      enlace.title = "Postularse con el Aplicador";
      enlace.addEventListener("click", (e) => {
        e.preventDefault(); // sin esto se abre el cliente de mail del sistema
        e.stopPropagation();
        abrirPanel(email, enlace);
      });
    }
  }

  function contenedorDelPost(chip) {
    // Recorremos los selectores en orden y no los ancestros: asi gana el contenedor mas
    // externo de la lista (el post entero, con el nombre de quien publica) y no el primer
    // ancestro que casualmente coincida (solo el parrafo del cuerpo).
    for (const sel of CONTENEDORES) {
      const contenedor = chip.closest(sel);
      if (contenedor && contenedor.innerText?.length > 120) return contenedor;
    }
    // Plan B: el primer ancestro con cuerpo suficiente como para ser el post.
    for (let p = chip.parentElement, saltos = 0; p && saltos < 15; p = p.parentElement, saltos++) {
      if (p.innerText?.length > 200) return p;
    }
    return chip.parentElement;
  }

  // Botones y contadores de la interfaz de LinkedIn, que el innerText arrastra junto al post.
  const RUIDO = /^(me gusta|recomendar|comentar|compartir|enviar|ver traducci[oó]n|ver m[aá]s|like|comment|share|send|repost|\d[\d.,]*\s*(comentarios?|reacciones|comments?|reactions?)?)$/i;

  function esRuido(linea) {
    // Las acciones pueden venir juntas en una sola linea separadas por puntos medios.
    // Solo la descartamos si TODAS las partes son ruido: "Consultora IT · 2 h" se queda.
    const partes = linea.split(/[·|•]/).map((p) => p.trim()).filter(Boolean);
    return partes.length > 0 && partes.every((p) => RUIDO.test(p));
  }

  function textoDelPost(contenedor, chip) {
    const crudo = contenedor?.innerText || chip.parentElement?.innerText || "";
    return crudo
      .split("\n")
      .filter((linea, i) => {
        const l = linea.trim();
        if (!l) return false;
        if (i === 0) return true; // la primera suele ser el autor
        return !esRuido(l);
      })
      .join("\n")
      .slice(0, 4000);
  }

  function autorDelPost(contenedor) {
    if (!contenedor) return "";
    for (const sel of AUTORES) {
      const nodo = contenedor.querySelector(sel);
      const texto = nodo?.innerText?.trim().split("\n")[0];
      if (texto && texto.length < 80) return texto;
    }
    // Plan B: la primera linea con contenido suele ser quien publica.
    const primera = contenedor.innerText?.trim().split("\n")[0]?.trim();
    return primera && primera.length < 80 ? primera : "";
  }

  function recorrer(raiz) {
    if (raiz.nodeType === Node.TEXT_NODE) {
      if (utilizable(raiz)) marcar(raiz);
      return;
    }
    if (raiz.nodeType !== Node.ELEMENT_NODE) return;

    // Los links mailto: van primero y por su cuenta, antes del filtro de PROHIBIDOS,
    // que existe para el recorrido de texto plano.
    marcarEnlaces(raiz);

    if (PROHIBIDOS.has(raiz.tagName)) return;

    const paseador = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) =>
        MAIL_TEST.test(n.nodeValue || "") && utilizable(n)
          ? NodeFilter.FILTER_ACCEPT
          : NodeFilter.FILTER_REJECT,
    });

    // Juntamos primero y modificamos despues: reemplazar nodos mientras se camina el
    // arbol deja al TreeWalker apuntando a algo que ya no existe.
    const encontrados = [];
    let n;
    while ((n = paseador.nextNode())) encontrados.push(n);
    encontrados.forEach(marcar);
  }

  // El feed carga infinito, asi que solo revisamos lo que va apareciendo.
  const pendientes = new Set();
  let programado = null;

  function procesar() {
    programado = null;
    const lote = [...pendientes];
    pendientes.clear();
    for (const nodo of lote) {
      if (nodo.isConnected) recorrer(nodo);
    }
  }

  function programar() {
    if (programado === null) programado = setTimeout(procesar, 350);
  }

  estilos();
  recorrer(document.body);

  new MutationObserver((registros) => {
    for (const registro of registros) {
      for (const nodo of registro.addedNodes) {
        if (nodo.nodeType === Node.ELEMENT_NODE) pendientes.add(nodo);
        else if (nodo.nodeType === Node.TEXT_NODE && nodo.parentElement) {
          pendientes.add(nodo.parentElement);
        }
      }
    }
    if (pendientes.size) programar();
  }).observe(document.body, { childList: true, subtree: true });
})();
