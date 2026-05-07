#!/usr/bin/env python3
"""
ESPERT Trade Marketing - Pre-geocodificador
===========================================
Correr UNA SOLA VEZ en tu maquina (requiere internet).
Genera geocache.json y luego reconstruye index.html con todas las
coordenadas embebidas:
  1) inyecta lat/lng en los arrays ADDRS_* (cadenas regulares)
  2) actualiza el bloque window.PRELOADED_GEOCACHE = {...} para que
     el mapa de la solapa "Nuevas Tecnologias" muestre todos los PDVs
     de POUCHES_DATA sin geocodificar en vivo.

Uso:
    python3 geocode_all.py

Requisitos: Python 3.7+, sin dependencias externas.
El proceso tarda ~1.15s por direccion (politica de Nominatim).
Se puede interrumpir con Ctrl+C y retomar: progreso queda en geocache.json.
"""
import json, urllib.request, urllib.parse, urllib.error
import time, os, sys, re

DIR = os.path.dirname(os.path.abspath(__file__))
ADDRS_FILE = os.path.join(DIR, 'addresses_to_geocode.json')
CACHE_FILE = os.path.join(DIR, 'geocache.json')
HTML_IN = os.path.join(DIR, 'index.html')
DELAY = 1.15

PRELOAD_BEGIN = '/* PRELOADED_GEOCACHE_BEGIN */'
PRELOAD_END = '/* PRELOADED_GEOCACHE_END */'


def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)


def clean_addr(addr):
    s = addr
    s = re.sub(r'\bS/?N\b', '', s, flags=re.IGNORECASE)
    s = re.sub(r'N\s*[°ºo]\s*0\b', '', s)
    s = s.replace('N°', '').replace('Nº', '').replace('Nro', '')
    s = re.sub(r'\bE/[^,]*', '', s)
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'\s*,\s*,', ',', s)
    s = re.sub(r',\s*$', '', s)
    return s.strip()


def geocode_one(address):
    queries = [address]
    cleaned = clean_addr(address)
    if cleaned and cleaned != address:
        queries.append(cleaned)
    for q in queries:
        url = ('https://nominatim.openstreetmap.org/search?q=' +
               urllib.parse.quote(q + ', Argentina') +
               '&format=json&limit=1&countrycodes=ar')
        req = urllib.request.Request(url, headers={
            'User-Agent': 'ESPERT-TradeMarketing-Geocoder/1.0',
            'Accept-Language': 'es',
        })
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read())
                    if data:
                        return {'lat': float(data[0]['lat']), 'lng': float(data[0]['lon'])}
                    break
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    print('  [429 Rate limited] Esperando 15s...')
                    time.sleep(15)
                else:
                    break
            except Exception:
                if attempt < 2:
                    time.sleep(3)
        time.sleep(DELAY)
    return None


def extract_pouches_addresses(html):
    m = re.search(r'window\.POUCHES_DATA\s*=\s*(\{.*?\});', html)
    if not m:
        return []
    data = json.loads(m.group(1))
    ciudades = data.get('ciudades', [])
    pdvs = data.get('pdvs', [])
    out = set()
    for r in pdvs:
        addr = r[0]
        ciudad = ciudades[r[1]] if 0 <= r[1] < len(ciudades) else ''
        full = f'{addr}, {ciudad}' if ciudad else addr
        out.add(full)
    return sorted(out)


def collect_pending_addresses():
    addrs = set()
    if os.path.exists(ADDRS_FILE):
        with open(ADDRS_FILE, encoding='utf-8') as f:
            for e in json.load(f):
                if e.get('address'):
                    addrs.add(e['address'])
    if os.path.exists(HTML_IN):
        with open(HTML_IN, encoding='utf-8') as f:
            html = f.read()
        for a in extract_pouches_addresses(html):
            addrs.add(a)
    return sorted(addrs)


def geocode_all():
    all_addrs = collect_pending_addresses()
    cache = load_cache()
    pending = [a for a in all_addrs if a not in cache]
    print(f'Total unicas: {len(all_addrs)} | Cacheadas: {len(cache)} | Pendientes: {len(pending)}')
    if not pending:
        print('Todo ya geocodificado.')
        return cache
    eta = len(pending) * DELAY / 60
    print(f'ETA aprox: ~{eta:.0f} min | Ctrl+C para pausar (progreso se guarda)\n')
    done = found = 0
    t0 = time.time()
    try:
        for addr in pending:
            result = geocode_one(addr)
            cache[addr] = result
            done += 1
            if result:
                found += 1
            if done % 10 == 0:
                save_cache(cache)
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed else 1
                eta_s = (len(pending) - done) / rate
                pct = done / len(pending) * 100
                print(f'  [{done}/{len(pending)}] {pct:.0f}% | encontradas: {found} | ETA: {eta_s/60:.0f}min', end='\r', flush=True)
            time.sleep(DELAY)
    except KeyboardInterrupt:
        print('\nInterrumpido. Guardando...')
    save_cache(cache)
    total_found = sum(1 for v in cache.values() if v)
    print(f'\nGeocaching: {total_found}/{len(cache)} encontradas ({total_found/max(len(cache),1)*100:.0f}%)')
    return cache


def inject_into_html(cache):
    if not os.path.exists(HTML_IN):
        print(f'ERROR: No se encuentra {HTML_IN}')
        return
    with open(HTML_IN, 'r', encoding='utf-8') as f:
        html = f.read()
    if os.path.exists(ADDRS_FILE):
        with open(ADDRS_FILE, encoding='utf-8') as f:
            all_entries = json.load(f)
        id_to_coords = {}
        for e in all_entries:
            coords = cache.get(e['address'])
            if coords:
                id_to_coords[e['id']] = coords
        print(f'Embebiendo coords en ADDRS_* para {len(id_to_coords)} PDVs...')

        def replace_entry(m):
            eid = int(m.group(1))
            if eid in id_to_coords:
                c = id_to_coords[eid]
                return f'[{m.group(1)},{m.group(2)},{m.group(3)},{c["lat"]:.6f},{c["lng"]:.6f}]'
            return m.group(0)

        html = re.sub(r'(\[\d+)(",[^"]+","[^"]+")(\])', replace_entry, html)
        old_mapper = 'return _d.map(function(x){return{id:x[0],label:x[1],address:x[2],lat:null,lng:null};})'
        new_mapper = 'return _d.map(function(x){return{id:x[0],label:x[1],address:x[2],lat:x[3]||null,lng:x[4]||null};})'
        html = html.replace(old_mapper, new_mapper)
        injected = len(re.findall(r'\[\d+,"[^"]+","[^"]+",-?\d+\.\d+', html))
        print(f'  PDVs con coords en HTML (ADDRS_*): {injected}')

    cache_clean = {k: v for k, v in cache.items() if v}
    blob = json.dumps(cache_clean, ensure_ascii=False, separators=(',', ':'))
    new_block = (PRELOAD_BEGIN + '\nwindow.PRELOADED_GEOCACHE = ' + blob + ';\n' + PRELOAD_END)
    if PRELOAD_BEGIN in html and PRELOAD_END in html:
        html = re.sub(re.escape(PRELOAD_BEGIN) + r'.*?' + re.escape(PRELOAD_END),
                      new_block, html, count=1, flags=re.DOTALL)
        print(f'  PRELOADED_GEOCACHE actualizado con {len(cache_clean)} entradas')
    else:
        anchor = 'var GEOCACHE_KEY = "espert_geocache_v2";'
        if anchor in html:
            html = html.replace(anchor, new_block + '\n' + anchor, 1)
            print(f'  PRELOADED_GEOCACHE insertado con {len(cache_clean)} entradas')

    with open(HTML_IN, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'HTML actualizado ({os.path.getsize(HTML_IN)//1024} KB)')


if __name__ == '__main__':
    print('=' * 55)
    print('  ESPERT Trade Marketing - Pre-geocodificador')
    print('=' * 55)
    cache = geocode_all()
    print('\nActualizando HTML...')
    inject_into_html(cache)
    print('\nListo. Abri index.html - mapas instantaneos.')
