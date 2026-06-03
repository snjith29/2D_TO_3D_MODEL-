#!/usr/bin/env python3
"""
Tile Unpacker: Extract tiles from MBTiles file and save as static PNG files.
Useful for offline use and distribution.
"""

import sqlite3
import logging
import argparse
from pathlib import Path

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

logger = logging.getLogger(__name__)


def unpack_mbtiles(mbtiles_path, output_dir, min_zoom=None, max_zoom=None):
    """
    Extract all tiles from an MBTiles file and save them as PNG files.
    
    Args:
        mbtiles_path: Path to MBTiles file
        output_dir: Directory to save unpacked tiles
        min_zoom: Minimum zoom level (optional)
        max_zoom: Maximum zoom level (optional)
    """
    mbtiles_path = Path(mbtiles_path)
    output_dir = Path(output_dir) / 'tiles'
    
    if not mbtiles_path.exists():
        logger.error(f"MBTiles file not found: {mbtiles_path}")
        return False
    
    try:
        conn = sqlite3.connect(str(mbtiles_path))
        cur = conn.cursor()
        
        # Get zoom range if not specified
        cur.execute('SELECT MIN(zoom_level), MAX(zoom_level) FROM tiles')
        db_min, db_max = cur.fetchone()
        
        if min_zoom is None:
            min_zoom = db_min
        if max_zoom is None:
            max_zoom = db_max
        
        logger.info(f"Unpacking tiles from zoom {min_zoom} to {max_zoom}")
        
        # Count total tiles
        cur.execute(
            'SELECT COUNT(*) FROM tiles WHERE zoom_level >= ? AND zoom_level <= ?',
            (min_zoom, max_zoom)
        )
        total = cur.fetchone()[0]
        logger.info(f"Total tiles to extract: {total}")
        
        # Extract tiles
        cur.execute(
            'SELECT zoom_level, tile_column, tile_row, tile_data FROM tiles WHERE zoom_level >= ? AND zoom_level <= ?',
            (min_zoom, max_zoom)
        )
        
        progress = tqdm(total=total, desc="Unpacking tiles") if HAS_TQDM else None
        count = 0
        
        for z, x, y, tile_data in cur.fetchall():
            # Convert TMS Y to XYZ (MBTiles standard is TMS)
            xyz_y = (1 << z) - 1 - y
            
            # Create directory structure
            tile_dir = output_dir / str(z) / str(x)
            tile_dir.mkdir(parents=True, exist_ok=True)
            
            # Write PNG file
            tile_file = tile_dir / f"{xyz_y}.png"
            with open(tile_file, 'wb') as f:
                f.write(tile_data)
            
            count += 1
            if progress:
                progress.update(1)
            elif count % 100 == 0:
                logger.info(f"Extracted {count}/{total} tiles...")
        
        if progress:
            progress.close()
        conn.close()
        
        logger.info(f"Successfully unpacked {count} tiles to {output_dir}")
        return True
        
    except Exception as e:
        logger.error(f"Error unpacking MBTiles: {e}")
        return False


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    parser = argparse.ArgumentParser(
        description='Extract tiles from MBTiles file for offline use'
    )
    parser.add_argument('mbtiles', help='Path to MBTiles file')
    parser.add_argument(
        '--output',
        default='output',
        help='Output directory (tiles will be in output/tiles/)'
    )
    parser.add_argument(
        '--min-zoom',
        type=int,
        help='Minimum zoom level'
    )
    parser.add_argument(
        '--max-zoom',
        type=int,
        help='Maximum zoom level'
    )
    
    args = parser.parse_args()
    
    success = unpack_mbtiles(
        args.mbtiles,
        args.output,
        min_zoom=args.min_zoom,
        max_zoom=args.max_zoom
    )
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
