#!/usr/bin/env python3
"""
ESPERT Trade Marketing — Pre-geocodificador
===========================================
Correr UNA SOLA VEZ en tu máquina (requiere internet).
Genera geocache.json y luego reconstruye CadenasKioscos.html
con todas las coordenadas embebidas.

Uso:
    python3 geocode_all.py

Requisitos: Python 3.7+, sin dependencias externas.

El proceso tarda ~30 min (1.1s por dirección, política de Nominatim).
Se puede interrumpir con Ctrl+C y retomar: guarda progreso en geocache.json.
"""
import json, urllib.request, urllib.parse, urllib.error
import time, os, sys, re

DIR        = os.path.dirname(os.path.abspath(__file__))
ADDRS_FILE = os.path.join(DIR, 'addresses_to_geocode.json')
CACHE_FILE = os.path.join(DIR, 'geocache.json')
HTML_IN    = os.path.join(DIR, 'CadenasKioscos.html')
DELAY      = 1.15

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)

def geocode_one(address):
    url = ('https://nominatim.openstreetmap.org/search?q=' +
           urllib.parse.quote(address + ', Argentina') +
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
                return None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print('  [429 Rate limited] Esperando 15s...')
                time.sleep(15)
            else:
                return None
        except Exception:
            if attempt < 2:
                time.sleep(3)
    return None

def geocode_all():
    if not os.path.exists(ADDRS_FILE):
        print(f'ERROR: No se encuentra {ADDRS_FILE}')
        sys.exit(1)

    with open(ADDRS_FILE, encoding='utf-8') as f:
        all_entries = json.load(f)

    unique_addrs = list({e['address'] for e in all_entries})
    cache = load_cache()
    pending = [a for a in unique_addrs if a not in cache]

    print(f'Total unicas: {len(unique_addrs)} | Cacheadas: {len(cache)} | Pendientes: {len(pending)}')
    if not pending:
        print('Todo ya geocodificado.')
        return cache

    eta = len(pending) * DELAY / 60
    print(f'ETA: ~{eta:.0f} min | Ctrl+C para pausar (progreso se guarda)\n')

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
        print(f'\nInterrumpido. Guardando...')

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

    with open(ADDRS_FILE, encoding='utf-8') as f:
        all_entries = json.load(f)

    id_to_coords = {}
    for e in all_entries:
        coords = cache.get(e['address'])
        if coords:
            id_to_coords[e['id']] = coords

    print(f'Embebiendo coordenadas para {len(id_to_coords)} PDVs...')

    def replace_entry(m):
        eid = int(m.group(1))
        if eid in id_to_coords:
            c = id_to_coords[eid]
            return f'[{m.group(1)},{m.group(2)},{m.group(3)},{c["lat"]:.6f},{c["lng"]:.6f}]'
        return m.group(0)

    new_html = re.sub(r'(\[\d+)(",[^"]+","[^"]+")(\])', replace_entry, html)

    old_mapper = 'return _d.map(function(x){return{id:x[0],label:x[1],address:x[2],lat:null,lng:null};})'
    new_mapper = 'return _d.map(function(x){return{id:x[0],label:x[1],address:x[2],lat:x[3]||null,lng:x[4]||null};})'
    new_html = new_html.replace(old_mapper, new_mapper)

    injected = len(re.findall(r'\[\d+,"[^"]+","[^"]+",-?\d+\.\d+', new_html))
    print(f'PDVs con coords en HTML: {injected}')

    with open(HTML_IN, 'w', encoding='utf-8') as f:
        f.write(new_html)
    print(f'HTML actualizado ({os.path.getsize(HTML_IN)//1024} KB)')

if __name__ == '__main__':
    print('=' * 55)
    print('  ESPERT Trade Marketing — Pre-geocodificador')
    print('=' * 55)
    cache = geocode_all()
    print('\nActualizando HTML...')
    inject_into_html(cache)
    print('\nListo. Abri CadenasKioscos.html — mapa instantaneo.')
