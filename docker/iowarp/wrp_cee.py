"""
wrp_cee wrapper module - provides simple function interface over ContextInterface.

This wrapper adapts the OOP ContextInterface API to the function-based API
that the bridge.py expects.
"""
import sys
sys.path.insert(0, '/usr/local/lib')

try:
    import wrp_cte_core_ext as cee
    _ctx_interface = None
    
    def _get_interface():
        """Lazy initialization of ContextInterface."""
        global _ctx_interface
        if _ctx_interface is None:
            _ctx_interface = cee.ContextInterface()
        return _ctx_interface
    
    def context_bundle(src, dst, format="arrow"):
        """Assimilate data into IOWarp storage.
        
        Args:
            src: str or list[str] - source path(s) with scheme (file::, folder::, hdf5::)
            dst: str - destination tag name
            format: str - data format (arrow, binary, hdf5, etc.)
        
        Returns:
            dict with status and tag
        """
        interface = _get_interface()
        
        # Handle single src or list of src
        sources = [src] if isinstance(src, str) else src
        
        # Create AssimilationCtx objects
        contexts = []
        for source in sources:
            ctx = cee.AssimilationCtx(
                src=source,
                dst=f"iowarp::{dst}",  # Add iowarp:: prefix
                format=format
            )
            contexts.append(ctx)
        
        # Assimilate
        result = interface.context_bundle(contexts)
        return {"status": "ok", "tag": dst}
    
    def context_query(tag_pattern="*", blob_pattern="*"):
        """Query for blobs matching patterns.
        
        Args:
            tag_pattern: str - glob pattern for tags
            blob_pattern: str - glob pattern for blob names
        
        Returns:
            list of dicts with tag/blob info
        """
        interface = _get_interface()
        
        # Convert glob to regex (simple conversion)
        import re
        tag_regex = tag_pattern.replace("*", ".*").replace("?", ".")
        blob_regex = blob_pattern.replace("*", ".*").replace("?", ".")
        
        try:
            blobs = interface.context_query(
                f"iowarp::{tag_regex}",  # Tag pattern with prefix
                blob_regex,              # Blob name regex
                0                        # Flags
            )
            
            # Parse blob results into list of dicts
            matches = []
            for blob in blobs:
                # blob might be a tuple/list or object with attributes
                if hasattr(blob, 'tag'):
                    matches.append({
                        'tag': blob.tag.replace('iowarp::', ''),
                        'blob_name': getattr(blob, 'blob_name', getattr(blob, 'name', ''))
                    })
                elif isinstance(blob, (tuple, list)) and len(blob) >= 2:
                    matches.append({
                        'tag': str(blob[0]).replace('iowarp::', ''),
                        'blob_name': str(blob[1])
                    })
                else:
                    matches.append({'tag': str(blob).replace('iowarp::', '')})
            
            return matches
        except Exception as e:
            # Return empty list on error (IOWarp may not have indexed data yet)
            return []
    
    def context_retrieve(tag, blob_name):
        """Retrieve blob data from IOWarp storage.
        
        Args:
            tag: str - tag name
            blob_name: str - blob identifier
        
        Returns:
            bytes - blob data
        """
        interface = _get_interface()
        
        # Use regex pattern to match exact blob name
        blob_regex = re.escape(blob_name)
        
        packed_data = interface.context_retrieve(
            f"iowarp::{tag}",  # Tag with prefix
            blob_regex,        # Blob name regex
            0                  # Flags
        )
        
        # packed_data is bytes
        return packed_data
    
    def context_destroy(tags):
        """Destroy context tag(s).
        
        Args:
            tags: str or list[str] - tag(s) to destroy
        """
        interface = _get_interface()
        
        # Handle single tag or list
        tag_list = [tags] if isinstance(tags, str) else tags
        
        # Add iowarp:: prefix to each tag
        prefixed_tags = [f"iowarp::{tag}" for tag in tag_list]
        
        interface.context_destroy(prefixed_tags)
        return {"status": "ok", "destroyed": tag_list}
    
    # Module is available
    __all__ = ['context_bundle', 'context_query', 'context_retrieve', 'context_destroy']

except ImportError as e:
    # wrp_cte_core_ext not available - provide stub functions
    import logging
    logging.warning(f"wrp_cte_core_ext import failed: {e} - using stub functions")
    
    def context_bundle(src, dst, format="arrow"):
        return {"status": "ok", "tag": dst, "stub": True}
    
    def context_query(tag_pattern="*", blob_pattern="*"):
        return []
    
    def context_retrieve(tag, blob_name):
        return None
    
    def context_destroy(tags):
        tag_list = [tags] if isinstance(tags, str) else tags
        return {"status": "ok", "destroyed": tag_list, "stub": True}
    
    __all__ = ['context_bundle', 'context_query', 'context_retrieve', 'context_destroy']
