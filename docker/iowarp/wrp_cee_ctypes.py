"""
Alternative wrp_cee implementation using ctypes to call C library directly.
This bypasses the broken Python nanobind extension.
"""
import ctypes
import os
import logging

logger = logging.getLogger(__name__)

# Try to load the C client library
try:
    # Load IOWarp C client library
    lib_path = "/usr/local/lib/libwrp_cte_core_client.so"
    if os.path.exists(lib_path):
        wrp_lib = ctypes.CDLL(lib_path)
        logger.info(f"✓ Loaded {lib_path}")
        HAS_CTYPES_WRP = True
    else:
        raise FileNotFoundError(f"Library not found: {lib_path}")
        
except Exception as e:
    logger.warning(f"Could not load C library: {e} - using stub")
    HAS_CTYPES_WRP = False


if HAS_CTYPES_WRP:
    # TODO: Define C function signatures and wrappers
    # This requires knowledge of the C API structure
    # For now, fall back to stub
    logger.warning("C library loaded but API mapping not implemented - using stub")
    HAS_CTYPES_WRP = False


if not HAS_CTYPES_WRP:
    # Use stub implementation
    import logging
    logging.warning("Using stub functions")
    
    # Stub storage for testing
    _stub_storage = {}
    
    def context_bundle(src, dst, format="arrow"):
        # Store file contents in stub storage
        sources = [src] if isinstance(src, str) else src
        if dst not in _stub_storage:
            _stub_storage[dst] = {}
        
        stored_count = 0
        for source in sources:
            if source.startswith("file::"):
                path = source[6:]  # Remove "file::" prefix
                try:
                    with open(path, 'rb') as f:
                        blob_name = path.split('/')[-1]
                        content = f.read()
                        _stub_storage[dst][blob_name] = content
                        stored_count += 1
                        logger.info(f"[STUB] Stored {blob_name} in tag '{dst}' ({len(content)} bytes)")
                except Exception as e:
                    logger.error(f"[STUB] Failed to store {path}: {e}")
        
        logger.info(f"[STUB] Storage state: {list(_stub_storage.keys())} tags, {sum(len(v) for v in _stub_storage.values())} blobs total")
        return {"status": "ok", "tag": dst, "stub": True, "stored": stored_count}
    
    def context_query(tag_pattern="*", blob_pattern="*"):
        return []
    
    def context_retrieve(tag, blob_name):
        # Retrieve from stub storage
        logger.info(f"[STUB] Retrieving '{blob_name}' from tag '{tag}'")
        logger.info(f"[STUB] Available tags: {list(_stub_storage.keys())}")
        
        if tag in _stub_storage:
            logger.info(f"[STUB] Available blobs in '{tag}': {list(_stub_storage[tag].keys())}")
            if blob_name in _stub_storage[tag]:
                data = _stub_storage[tag][blob_name]
                logger.info(f"[STUB] Retrieved {len(data)} bytes")
                return data
            else:
                logger.warning(f"[STUB] Blob '{blob_name}' not found in tag '{tag}'")
        else:
            logger.warning(f"[STUB] Tag '{tag}' not found")
        
        return None
    
    def context_destroy(tags):
        # Remove from stub storage
        tag_list = [tags] if isinstance(tags, str) else tags
        for tag in tag_list:
            if tag in _stub_storage:
                del _stub_storage[tag]
        return {"status": "ok", "destroyed": tag_list, "stub": True}
    
    def get_stub_state():
        """Debug function to inspect stub storage state."""
        return {
            "tags": list(_stub_storage.keys()),
            "blobs": {tag: list(blobs.keys()) for tag, blobs in _stub_storage.items()},
            "total_size": sum(sum(len(v) for v in blobs.values()) for blobs in _stub_storage.values())
        }
