#!/bin/bash
# AgentFactory Complete Demo Script
# Shows: Ingest → Cache HITs → Flush → IOWarp Fallback

set -e

echo "=========================================="
echo "AgentFactory Demo - Two-Tier Storage"
echo "=========================================="
echo ""

# Check infrastructure
echo "📋 Step 1: Checking infrastructure..."
if ! docker-compose ps | grep -q "Up (healthy)"; then
    echo "Starting containers..."
    docker-compose up -d
    sleep 5
fi
docker-compose ps
echo ""

# Part 1: Normal flow with cache
echo "=========================================="
echo "📥 PART 1: Ingest & Retrieve (Cache HITs)"
echo "=========================================="
echo ""
echo "Running: Ingest 3 files → Retrieve → Check cache stats"
echo "Expected: 100% cache hit rate"
echo ""
read -p "Press Enter to start..."
echo ""

uv run cli.py < DEMO_PART1.txt

echo ""
echo "✅ Part 1 Complete!"
echo ""
echo "What happened:"
echo "  • Ingested 3 files → IOWarp shared memory + Memcached"
echo "  • Retrieved from cache → HIT! (reward: +0.30)"
echo "  • Retrieved again → HIT! (100% hit rate)"
echo "  • Query returned 0 (C++ extension broken)"
echo ""
read -p "Press Enter to flush cache..."
echo ""

# Flush cache
echo "=========================================="
echo "🗑️  FLUSHING MEMCACHED CACHE"
echo "=========================================="
echo ""
printf "flush_all\r\n" | nc -w 1 127.0.0.1 11211
echo "✅ Cache flushed! All memcached data cleared."
echo "   IOWarp shared memory still has data..."
echo ""
read -p "Press Enter to retrieve from IOWarp..."
echo ""

# Part 2: Retrieve after flush
echo "=========================================="
echo "📤 PART 2: Retrieve After Flush (IOWarp)"
echo "=========================================="
echo ""
echo "Running: Retrieve same files"
echo "Expected: Cache MISS → Fetch from IOWarp"
echo ""

uv run cli.py < DEMO_PART2_after_flush.txt

echo ""
echo "✅ Part 2 Complete!"
echo ""
echo "What happened:"
echo "  • Cache was empty (flushed)"
echo "  • Retrieves went to IOWarp → MISS (reward: +0.20)"
echo "  • Proves data persisted in IOWarp shared memory!"
echo ""

# Summary
echo "=========================================="
echo "📊 DEMO SUMMARY"
echo "=========================================="
echo ""
echo "✅ Working:"
echo "   • Ingest: Stores in IOWarp + Memcached"
echo "   • Retrieve: Cache-aside pattern (cache → IOWarp fallback)"
echo "   • Two-tier storage: Fast cache + persistent backend"
echo "   • Persistence: Data survives cache flush"
echo ""
echo "❌ Not Working:"
echo "   • Query/list_blobs: Returns 0 (C++ extension ABI mismatch)"
echo "   • Root cause: undefined symbol: PyExc_ValueError"
echo ""
echo "🏗️  Architecture:"
echo "   Memcached (512MB RAM) ←→ IOWarp (8GB shared memory)"
echo "        ↓ Fast                     ↓ Persistent"
echo "   Cache HITs                  Fallback storage"
echo ""
echo "Demo complete! 🎉"
