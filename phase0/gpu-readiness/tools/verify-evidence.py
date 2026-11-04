#!/usr/bin/env python3
"""Verify readiness package integrity using the preserved verifier; no runtime promotion."""
import importlib.util
from pathlib import Path

PACKAGE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('preserved_evidence_verifier',PACKAGE.parent/'gpu-recovery/tools/verify-evidence.py')
verifier=importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)

if __name__=='__main__':
    print('phase0/gpu-readiness: PASS',verifier.verify_index(PACKAGE),'artifacts (integrity only)')
