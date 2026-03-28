#!/usr/bin/env python3
"""
Wide Vector Generator for LLM Model.

Creates a single SQL row with all symbols' ticker info and indicators
as a wide vector for LLM buy/sell decision making.

Format:
[symbol1_price, symbol1_rsi, symbol1_sma20, ..., symbol2_price, symbol2_rsi, ...]

Architecture:
- Reads ticker data from ticker_24hr_stats table
- Reads indicators from candle_indicators table (calculated by EnrichmentService)
- No waiting/synchronization - reads whatever is in DB
- EnrichmentService runs async and keeps indicators up-to-date
"""

import asyncio
import asyncpg
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WideVectorGenerator:
    """
    Generate wide vector from ticker and indicator data.

    Creates a single row with all symbols' data as columns for LLM input.
    
    Flow:
    1. Connect to database
    2. Load latest ticker data for all symbols
    3. Load latest indicators for all symbols (if available)
    4. Build flat vector: [symbol1_features, symbol2_features, ...]
    5. Save to JSON and NumPy formats
    
    Note: Does NOT wait for enrichment. Reads whatever is in DB.
    """

    def __init__(
        self,
        db_url: str,
        symbols: Optional[List[str]] = None,
        include_indicators: bool = True,
    ) -> None:
        """
        Initialize vector generator.

        Args:
            db_url: PostgreSQL connection URL
            symbols: List of symbols to include (None = all active)
            include_indicators: Include indicator columns
        """
        self.db_url = db_url
        self.symbols = symbols
        self.include_indicators = include_indicators
        self.db_pool = None
        self._symbol_list: List[str] = []

    async def connect(self) -> None:
        """Connect to database."""
        self.db_pool = await asyncpg.create_pool(
            self.db_url,
            min_size=2,
            max_size=10,
        )
        await self._load_symbols()

    async def disconnect(self) -> None:
        """Disconnect from database."""
        if self.db_pool:
            await self.db_pool.close()

    async def _load_symbols(self) -> None:
        """Load symbol list from database."""
        async with self.db_pool.acquire() as conn:
            if self.symbols:
                rows = await conn.fetch(
                    """
                    SELECT id, symbol, base_asset, quote_asset
                    FROM symbols
                    WHERE symbol = ANY($1) AND is_active = true AND is_allowed = true
                    ORDER BY symbol
                    """,
                    self.symbols
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, symbol, base_asset, quote_asset
                    FROM symbols
                    WHERE is_active = true AND is_allowed = true
                    ORDER BY symbol
                    """
                )

            self._symbol_list = [row['symbol'] for row in rows]
            logger.info(f"Loaded {len(self._symbol_list)} symbols")

    async def generate_wide_vector(self) -> Optional[Dict[str, Any]]:
        """
        Generate wide vector for all symbols.

        Simply reads from database - no waiting for enrichment.
        Indicators are included if EnrichmentService has calculated them.

        Returns:
            Dictionary with:
            - timestamp: When vector was generated
            - symbols: List of symbols in order
            - vector: Flat numpy array of values
            - column_names: Names for each column
            - metadata: Additional info
        """
        async with self.db_pool.acquire() as conn:
            # Get latest ticker data for all symbols
            ticker_data = await self._get_latest_tickers(conn)

            if not ticker_data:
                logger.warning("No ticker data found")
                return None

            # Get latest indicators for all symbols (if available)
            indicator_data: Dict[str, Dict[str, float]] = {}
            indicators_found = 0
            
            if self.include_indicators:
                indicator_data = await self._get_latest_indicators(conn)
                indicators_found = sum(len(v) for v in indicator_data.values())

            if indicators_found == 0:
                logger.info("No indicators found in DB (EnrichmentService may not be running)")

            # Build wide vector
            vector = self._build_wide_vector(ticker_data, indicator_data)

            return {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'symbols': self._symbol_list,
                'vector': vector['values'],
                'column_names': vector['columns'],
                'metadata': {
                    'total_columns': len(vector['columns']),
                    'symbols_count': len(self._symbol_list),
                    'includes_indicators': self.include_indicators,
                    'indicators_found': indicators_found,
                    'null_count': vector['null_count'],
                }
            }

    async def _get_latest_tickers(
        self,
        conn: asyncpg.Connection
    ) -> Dict[str, Dict[str, Any]]:
        """Get latest ticker data for all symbols."""
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (t.symbol_id)
                s.symbol,
                t.last_price,
                t.open_price,
                t.high_price,
                t.low_price,
                t.total_volume,
                t.total_quote_volume,
                t.price_change,
                t.price_change_pct,
                t.time
            FROM ticker_24hr_stats t
            JOIN symbols s ON s.id = t.symbol_id
            WHERE s.is_active = true AND s.is_allowed = true
            ORDER BY t.symbol_id, t.time DESC
            """
        )

        return {
            row['symbol']: {
                'last_price': float(row['last_price']) if row['last_price'] else 0.0,
                'open_price': float(row['open_price']) if row['open_price'] else 0.0,
                'high_price': float(row['high_price']) if row['high_price'] else 0.0,
                'low_price': float(row['low_price']) if row['low_price'] else 0.0,
                'volume': float(row['total_volume']) if row['total_volume'] else 0.0,
                'quote_volume': float(row['total_quote_volume']) if row['total_quote_volume'] else 0.0,
                'price_change': float(row['price_change']) if row['price_change'] else 0.0,
                'price_change_pct': float(row['price_change_pct']) if row['price_change_pct'] else 0.0,
            }
            for row in rows
        }

    async def _get_latest_indicators(
        self,
        conn: asyncpg.Connection
    ) -> Dict[str, Dict[str, float]]:
        """Get latest indicator data for all symbols."""
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (t.symbol_id)
                s.symbol,
                t.values
            FROM candle_indicators t
            JOIN symbols s ON s.id = t.symbol_id
            WHERE s.is_active = true AND s.is_allowed = true
            ORDER BY t.symbol_id, t.time DESC
            """
        )

        result = {}
        for row in rows:
            symbol = row['symbol']
            values_raw = row['values']
            
            # Handle JSONB - can be dict, string, or list
            if values_raw is None:
                values: Dict[str, Any] = {}
            elif isinstance(values_raw, dict):
                values = values_raw
            elif isinstance(values_raw, str):
                values = json.loads(values_raw)
            elif isinstance(values_raw, (list, tuple)):
                # Convert list of [key, value] pairs to dict
                values = dict(values_raw) if len(values_raw) > 0 else {}
            else:
                values = {}
            
            result[symbol] = {k: float(v) if v is not None else 0.0 for k, v in values.items()}

        return result

    def _build_wide_vector(
        self,
        ticker_data: Dict[str, Dict[str, Any]],
        indicator_data: Dict[str, Dict[str, float]]
    ) -> Dict[str, Any]:
        """Build wide vector from ticker and indicator data."""
        values = []
        columns = []
        null_count = 0

        for symbol in self._symbol_list:
            ticker = ticker_data.get(symbol, {})
            indicators = indicator_data.get(symbol, {})

            # Ticker columns (always included)
            ticker_fields = [
                ('last_price', ticker.get('last_price', 0.0)),
                ('open_price', ticker.get('open_price', 0.0)),
                ('high_price', ticker.get('high_price', 0.0)),
                ('low_price', ticker.get('low_price', 0.0)),
                ('volume', ticker.get('volume', 0.0)),
                ('quote_volume', ticker.get('quote_volume', 0.0)),
                ('price_change', ticker.get('price_change', 0.0)),
                ('price_change_pct', ticker.get('price_change_pct', 0.0)),
            ]

            for field_name, value in ticker_fields:
                columns.append(f"{symbol}_{field_name}")
                values.append(value if value is not None else 0.0)
                if value is None:
                    null_count += 1

            # Indicator columns (if enabled)
            if self.include_indicators:
                for ind_key in sorted(indicators.keys()):
                    value = indicators.get(ind_key, 0.0)
                    columns.append(f"{symbol}_{ind_key}")
                    values.append(value if value is not None else 0.0)
                    if value is None:
                        null_count += 1

        return {
            'values': np.array(values, dtype=np.float32),
            'columns': columns,
            'null_count': null_count,
        }

    def vector_to_json(self, vector_data: Dict[str, Any], compress: bool = True) -> str:
        """Convert vector to JSON string."""
        if compress:
            output = {
                'timestamp': vector_data['timestamp'],
                'symbols_count': vector_data['metadata']['symbols_count'],
                'vector_size': len(vector_data['vector']),
                'vector': vector_data['vector'].tolist(),
                'column_names': vector_data['column_names'],
            }
        else:
            output = {**vector_data, 'vector': vector_data['vector'].tolist()}
        return json.dumps(output, indent=2)

    def vector_to_dict(self, vector_data: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
        """Convert vector to nested dictionary."""
        result = {}
        values = vector_data['vector']
        columns = vector_data['column_names']

        for symbol in self._symbol_list:
            symbol_data = {}
            for i, col in enumerate(columns):
                if col.startswith(f"{symbol}_"):
                    feature = col[len(symbol)+1:]
                    symbol_data[feature] = float(values[i])
            result[symbol] = symbol_data
        return result


async def test_wide_vector_generator() -> None:
    """Test wide vector generation."""
    db_url = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"

    print("=" * 70)
    print("Wide Vector Generator Test for LLM Model")
    print("=" * 70)
    print()
    print("Architecture: Reads from DB (no waiting for enrichment)")
    print("Indicators: Included if EnrichmentService has calculated them")
    print()

    generator = WideVectorGenerator(
        db_url=db_url,
        symbols=None,
        include_indicators=True,
    )

    try:
        await generator.connect()
        print(f"Symbols loaded: {len(generator._symbol_list)}")
        print()

        print("Generating wide vector...")
        vector_data = await generator.generate_wide_vector()

        if not vector_data:
            print("ERROR: No data generated")
            return

        print()
        print("=" * 70)
        print("VECTOR STATISTICS")
        print("=" * 70)
        print(f"Timestamp: {vector_data['timestamp']}")
        print(f"Symbols: {vector_data['metadata']['symbols_count']}")
        print(f"Total columns: {vector_data['metadata']['total_columns']}")
        print(f"Vector size: {len(vector_data['vector'])} floats")
        print(f"Indicators found: {vector_data['metadata']['indicators_found']}")
        print(f"Null values: {vector_data['metadata']['null_count']}")
        print()

        # Show sample columns
        print()
        print("=" * 70)
        print("SAMPLE COLUMNS (first 3 symbols)")
        print("=" * 70)
        for i in range(min(3, len(generator._symbol_list))):
            symbol = generator._symbol_list[i]
            symbol_cols = [c for c in vector_data['column_names'] if c.startswith(f"{symbol}_")]
            print(f"\n{symbol}:")
            for col in symbol_cols[:10]:  # Show first 10 columns per symbol
                idx = vector_data['column_names'].index(col)
                value = vector_data['vector'][idx]
                print(f"  {col}: {value:.4f}")
            if len(symbol_cols) > 10:
                print(f"  ... and {len(symbol_cols) - 10} more")

        print()
        print("=" * 70)
        print("SAVING TO FILES")
        print("=" * 70)

        json_file = '/tmp/wide_vector_llm.json'
        with open(json_file, 'w') as f:
            f.write(generator.vector_to_json(vector_data))
        print(f"✓ Saved JSON to: {json_file}")

        npy_file = '/tmp/wide_vector_llm.npy'
        np.save(npy_file, vector_data['vector'])
        print(f"✓ Saved NumPy array to: {npy_file}")

        cols_file = '/tmp/wide_vector_columns.json'
        with open(cols_file, 'w') as f:
            json.dump({
                'columns': vector_data['column_names'],
                'symbols': vector_data['symbols'],
                'metadata': vector_data['metadata'],
            }, f, indent=2)
        print(f"✓ Saved column names to: {cols_file}")

        print()
        print("=" * 70)
        print("TEST COMPLETE")
        print("=" * 70)
        print()
        print("Usage in LLM model:")
        print("  import numpy as np")
        print("  vector = np.load('/tmp/wide_vector_llm.npy')")
        print("  # Pass to your LLM for buy/sell decision")
        print()

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await generator.disconnect()


if __name__ == '__main__':
    asyncio.run(test_wide_vector_generator())
