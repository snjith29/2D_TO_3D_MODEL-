#!/usr/bin/env python3
"""
Simple map server: serves MBTiles tiles at /tiles/{z}/{x}/{y}.png
and accepts POST /set_geo to update output/plan.json metadata.
"""
import json
import sqlite3
import logging
from http.server import SimpleHTTPRequestHandler, HTTPServer
from socketserver import TCPServer
from urllib.parse import urlparse
from pathlib import Path
import os
import io

logger = logging.getLogger(__name__)

# MBTiles format detection cache
_mbtiles_format_cache = {}


def detect_mbtiles_format(mbtiles_path):
    """
    Detect if MBTiles uses XYZ or TMS tile indexing.
    Returns 'xyz' or 'tms' based on tile data.
    Cached per file to avoid repeated queries.
    """
    if mbtiles_path in _mbtiles_format_cache:
        return _mbtiles_format_cache[mbtiles_path]
    
    try:
        conn = sqlite3.connect(str(mbtiles_path))
        cur = conn.cursor()
        
        # Check metadata for format hint
        cur.execute('SELECT value FROM metadata WHERE name = ?', ('format',))
        row = cur.fetchone()
        if row and row[0]:
            fmt = row[0].lower()
            if 'xyz' in fmt:
                _mbtiles_format_cache[mbtiles_path] = 'xyz'
                conn.close()
                return 'xyz'
            elif 'tms' in fmt:
                _mbtiles_format_cache[mbtiles_path] = 'tms'
                conn.close()
                return 'tms'
        
        # Heuristic: check max zoom level and tile distribution
        # Most web maps use XYZ; traditional OSM-style TMS flips Y
        cur.execute('SELECT COUNT(*) FROM tiles WHERE zoom_level = (SELECT MAX(zoom_level) FROM tiles)')
        count = cur.fetchone()[0]
        
        # If we have data, assume TMS by default (OSM standard)
        # Can be overridden in metadata or by tile inspection
        fmt = 'tms'
        _mbtiles_format_cache[mbtiles_path] = fmt
        conn.close()
        return fmt
        
    except Exception as e:
        logger.warning(f"Could not detect MBTiles format: {e}, defaulting to TMS")
        _mbtiles_format_cache[mbtiles_path] = 'tms'
        return 'tms'


def read_tile_from_mbtiles(mbtiles_path, z, x, y):
    """
    Read a tile from MBTiles, auto-detecting format.
    Returns tile data or None.
    """
    try:
        fmt = detect_mbtiles_format(mbtiles_path)
        
        conn = sqlite3.connect(str(mbtiles_path))
        cur = conn.cursor()
        
        # TMS stores Y flipped; XYZ stores Y as-is
        if fmt == 'tms':
            # Convert XYZ to TMS
            query_y = (1 << z) - 1 - y
        else:
            # Use XYZ as-is
            query_y = y
        
        cur.execute(
            'SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?',
            (z, x, query_y)
        )
        row = cur.fetchone()
        conn.close()
        
        if row and row[0]:
            return row[0]
        return None
    except Exception as e:
        logger.warning(f"Error reading tile from MBTiles: {e}")
        return None


class MapHandler(SimpleHTTPRequestHandler):
    # class-level config set by run_server
    mbtiles_path = None
    output_dir = None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith('/tiles/'):
            # expected /tiles/{z}/{x}/{y}.png
            parts = path.split('/')
            try:
                _, _tiles, z, x, yfile = parts
            except ValueError:
                self.send_error(404)
                return

            y = yfile.split('.')[0]
            try:
                z_i = int(z); x_i = int(x); y_i = int(y)
            except ValueError:
                self.send_error(404)
                return

            # Serve from MBTiles if available
            if MapHandler.mbtiles_path and Path(MapHandler.mbtiles_path).exists():
                data = read_tile_from_mbtiles(MapHandler.mbtiles_path, z_i, x_i, y_i)
                if data:
                    self.send_response(200)
                    self.send_header('Content-type', 'image/png')
                    self.send_header('Content-length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return

            # Fallback to static files under output/tiles/
            tile_file = Path(MapHandler.output_dir) / 'tiles' / z / x / f"{y}.png"
            if tile_file.exists():
                return SimpleHTTPRequestHandler.do_GET(self)

            self.send_error(404)
            return

        # Default file server behavior
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == '/set_geo':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body.decode('utf-8'))
                lat = float(data.get('lat'))
                lon = float(data.get('lon'))
                zoom = int(data.get('zoom')) if data.get('zoom') is not None else None

                plan_path = Path(MapHandler.output_dir) / 'plan.json'
                if plan_path.exists():
                    with open(plan_path, 'r', encoding='utf-8') as f:
                        plan = json.load(f)
                else:
                    plan = {}

                meta = plan.get('metadata', {})
                meta['lat'] = lat
                meta['lon'] = lon
                if zoom is not None:
                    meta['zoom'] = zoom
                plan['metadata'] = meta

                with open(plan_path, 'w', encoding='utf-8') as f:
                    json.dump(plan, f, indent=2)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'ok'}).encode('utf-8'))
                return

            except Exception as e:
                logger.error(f"Error handling set_geo: {e}")
                self.send_error(400)
                return

        # Otherwise not allowed
        self.send_error(404)


def run_server(output_dir, mbtiles_path=None, port=8000):
    MapHandler.mbtiles_path = mbtiles_path
    MapHandler.output_dir = str(output_dir)

    os.chdir(str(Path(__file__).parent))

    with TCPServer(('', port), MapHandler) as httpd:
        url = f'http://localhost:{port}/viewer/index.html'
        logger.info(f"Serving site at {url}")
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info('Server stopped')


if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser()
    p.add_argument('--output', default='output')
    p.add_argument('--map', default=None)
    p.add_argument('--port', type=int, default=8000)
    args = p.parse_args()
    run_server(args.output, args.map, args.port)
