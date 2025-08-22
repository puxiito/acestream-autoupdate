# Acestream Auto-Update (plantilla)

Automatiza la actualización de una lista `M3U` en GitHub con enlaces `acestream://` (o `http(s)`/`m3u8`) que se extraen de páginas web.

> ⚠️ **Aviso legal:** respeta siempre los Términos de Uso y la legalidad de tu país. No hagas scraping ni redistribuyas contenidos protegidos sin permiso. Revisa también `robots.txt` de los sitios.

## Estructura

```
.
├── channels.yaml              # Configuración de canales (fuentes y reglas de extracción)
├── lista.m3u                  # Lista generada/actualizada
├── scraper
│   ├── requirements.txt
│   └── update_m3u.py
└── .github
    └── workflows
        └── update.yml
```

## Configuración rápida

1. Edita **`channels.yaml`** con tus canales. Ejemplos incluidos:
   - `regex`: busca directamente `acestream://<hash>` en el HTML.
   - `selector` + `attr` + `inner_regex`: selecciona un elemento y extrae el enlace/ID.
   - `fixed_url`: usa una URL fija si no quieres scraping.

2. Opcional: modifica atributos `EXTINF` en `attrs` (ej. `group-title`, `tvg-logo`).

3. **Prueba localmente**:
   ```bash
   pip install -r scraper/requirements.txt
   python scraper/update_m3u.py --dry-run   # solo muestra cambios
   python scraper/update_m3u.py             # escribe lista.m3u si hay cambios
   ```

4. **GitHub Actions**: ya está configurado para ejecutarse cada 6 horas y cuando lo lances manualmente desde la pestaña *Actions*.
   - Asegúrate de que el workflow tenga permisos `contents: write` (ya declarado).

## Cómo personalizar la extracción

- Si la página publica directamente `acestream://<hash>`, usa `regex`:
  ```yaml
  regex: "acestream://[0-9a-fA-F]{40}"
  ```

- Si la página solo muestra el **hash** (40 hex), también sirve. El script añadirá el prefijo `acestream://` automáticamente. Por ejemplo:
  ```yaml
  inner_regex: "[0-9a-fA-F]{40}"
  ```

- Si el enlace está en un botón/enlace/atributo concreto:
  ```yaml
  selector: "a.boton-play"
  attr: "href"
  inner_regex: "acestream://[0-9a-fA-F]{40}"
  ```

> Consejo: abre las Herramientas de Desarrollador del navegador (F12), inspecciona el elemento que contiene el enlace/hash y construye el selector/regex a partir de ahí.

## Mantenimiento

- Si un sitio cambia su HTML, quizá debas ajustar `regex` o `selector`.
- Si un canal falla temporalmente, el script intenta **mantener el último enlace válido** que haya en `lista.m3u` para no romper tu playlist.
- Los cambios se comiten automáticamente con `git-auto-commit-action` cuando `lista.m3u` cambia.

¡Listo! Edita `channels.yaml` con tus fuentes reales y tendrás una URL fija en GitHub (por ejemplo `https://raw.githubusercontent.com/<tuusuario>/<tu-repo>/main/lista.m3u`) que puedes usar en VLC.
