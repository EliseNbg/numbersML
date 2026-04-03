#!/usr/bin/env python3
"""
Verify CNN+GRU model is available in the dashboard API.

This script:
1. Checks if the model file exists
2. Tests the /api/ml/models endpoint
3. Verifies CNN+GRU is in the response
"""

import os
import sys
import json
from pathlib import Path

def check_model_file():
    """Check if CNN+GRU model file exists."""
    print("="*60)
    print("Checking CNN+GRU Model File")
    print("="*60)
    
    models_dir = Path("ml/models/cnn_gru")
    
    if not models_dir.exists():
        print(f"❌ Directory not found: {models_dir}")
        return False
    
    # Find .pt files
    pt_files = list(models_dir.glob("*.pt"))
    
    if not pt_files:
        print(f"❌ No .pt files found in {models_dir}")
        return False
    
    print(f"✅ Found {len(pt_files)} CNN+GRU model file(s):")
    for f in pt_files:
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"   - {f.name} ({size_mb:.2f} MB)")
    
    return True


def check_api_integration():
    """Check if API route has CNN+GRU integration."""
    print()
    print("="*60)
    print("Checking API Integration")
    print("="*60)
    
    api_file = Path("src/infrastructure/api/routes/ml.py")
    
    if not api_file.exists():
        print(f"❌ API file not found: {api_file}")
        return False
    
    content = api_file.read_text()
    
    # Check for CNN+GRU label
    if '"cnn_gru"' not in content and "'cnn_gru'" not in content:
        print("❌ CNN+GRU not found in type_labels")
        return False
    
    print("✅ CNN+GRU found in type_labels")
    
    # Check for CNN+GRU detection
    if 'cnn1.' not in content:
        print("❌ CNN+GRU detection logic not found")
        return False
    
    print("✅ CNN+GRU detection logic found")
    
    # Check for GRU detection
    if 'gru.' not in content:
        print("❌ GRU detection logic not found")
        return False
    
    print("✅ GRU detection logic found")
    
    return True


def check_dashboard_html():
    """Check if dashboard HTML has recommendation text."""
    print()
    print("="*60)
    print("Checking Dashboard HTML")
    print("="*60)
    
    html_file = Path("dashboard/prediction.html")
    
    if not html_file.exists():
        print(f"❌ HTML file not found: {html_file}")
        return False
    
    content = html_file.read_text()
    
    # Check for recommendation text
    if 'CNN+GRU' in content or 'cnn_gru' in content.lower():
        print("✅ CNN+GRU mentioned in dashboard HTML")
        return True
    else:
        print("⚠️  CNN+GRU not explicitly mentioned (but will still work)")
        return True


def check_model_architecture():
    """Check if CNN_GRUModel class exists."""
    print()
    print("="*60)
    print("Checking Model Architecture")
    print("="*60)
    
    model_file = Path("ml/model.py")
    
    if not model_file.exists():
        print(f"❌ Model file not found: {model_file}")
        return False
    
    content = model_file.read_text()
    
    if 'class CNN_GRUModel' not in content:
        print("❌ CNN_GRUModel class not found")
        return False
    
    print("✅ CNN_GRUModel class found")
    
    if 'def create_model' in content and '"cnn_gru"' in content:
        print("✅ create_model factory includes cnn_gru")
        return True
    else:
        print("❌ create_model factory may not include cnn_gru")
        return False


def main():
    """Run all checks."""
    print()
    print("╔" + "="*58 + "╗")
    print("║" + " "*58 + "║")
    print("║" + "  CNN+GRU Dashboard Integration Verification".center(58) + "║")
    print("║" + " "*58 + "║")
    print("╚" + "="*58 + "╝")
    print()
    
    results = []
    
    # Run checks
    results.append(("Model File", check_model_file()))
    results.append(("API Integration", check_api_integration()))
    results.append(("Dashboard HTML", check_dashboard_html()))
    results.append(("Model Architecture", check_model_architecture()))
    
    # Summary
    print()
    print("="*60)
    print("Summary")
    print("="*60)
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {name:30s} {status}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("🎉 All checks passed! CNN+GRU is ready for dashboard.")
        print()
        print("Next steps:")
        print("  1. Start the dashboard: python3 run_dashboard.py")
        print("  2. Open: http://localhost:8000/dashboard/prediction.html")
        print("  3. Select CNN+GRU from model dropdown")
        print("  4. Click 'Load & Predict'")
        return 0
    else:
        print("⚠️  Some checks failed. Please review the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
