#!/bin/bash

# Installation script for Credit Report PDF Table Extractor
# This script installs all dependencies (basic and optional)

echo "=============================================================================="
echo "  Credit Report PDF Table Extractor - Installation Script"
echo "=============================================================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or later."
    exit 1
fi

echo "✓ Python 3 found: $(python3 --version)"
echo ""

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is not installed. Please install pip."
    exit 1
fi

echo "✓ pip3 found: $(pip3 --version)"
echo ""

# Ask user which installation type
echo "Select installation type:"
echo "  1) Basic (pdfplumber only - recommended)"
echo "  2) Full (all extraction libraries - requires additional system dependencies)"
echo ""
read -p "Enter choice [1-2]: " choice

case $choice in
    1)
        echo ""
        echo "Installing basic dependencies..."
        echo "------------------------------------------------------------------------------"
        pip3 install pdfplumber pandas openpyxl
        
        if [ $? -eq 0 ]; then
            echo ""
            echo "✓ Basic installation complete!"
            echo ""
            echo "You can now use:"
            echo "  - pdf_table_extractor.py"
            echo "  - example_usage.py"
            echo ""
            echo "To test: python3 test_extractor.py your_file.pdf"
        else
            echo "❌ Installation failed. Please check the error messages above."
            exit 1
        fi
        ;;
        
    2)
        echo ""
        echo "Full installation requires additional system dependencies."
        echo ""
        
        # Check OS
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            echo "Detected macOS"
            echo ""
            
            # Check if Homebrew is installed
            if ! command -v brew &> /dev/null; then
                echo "⚠️  Homebrew not found. Install from https://brew.sh/"
                echo "   Then run: brew install ghostscript openjdk"
            else
                echo "Installing system dependencies with Homebrew..."
                brew install ghostscript openjdk
            fi
            
        elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
            # Linux
            echo "Detected Linux"
            echo ""
            echo "Installing system dependencies..."
            
            if command -v apt-get &> /dev/null; then
                sudo apt-get update
                sudo apt-get install -y ghostscript python3-tk default-jre
            elif command -v yum &> /dev/null; then
                sudo yum install -y ghostscript python3-tkinter java-11-openjdk
            else
                echo "⚠️  Please manually install: ghostscript, tkinter, Java JRE"
            fi
        else
            echo "⚠️  Unsupported OS. Please manually install:"
            echo "   - Ghostscript"
            echo "   - Java Runtime Environment"
        fi
        
        echo ""
        echo "Installing Python packages..."
        echo "------------------------------------------------------------------------------"
        pip3 install pdfplumber pandas openpyxl
        pip3 install "camelot-py[cv]"
        pip3 install tabula-py
        pip3 install pdfminer.six
        
        if [ $? -eq 0 ]; then
            echo ""
            echo "✓ Full installation complete!"
            echo ""
            echo "You can now use:"
            echo "  - pdf_table_extractor.py (pdfplumber)"
            echo "  - alternative_extractors.py (Camelot, Tabula)"
            echo "  - example_usage.py"
            echo ""
            echo "To test: python3 test_extractor.py your_file.pdf"
        else
            echo "❌ Installation failed. Please check the error messages above."
            exit 1
        fi
        ;;
        
    *)
        echo "Invalid choice. Exiting."
        exit 1
        ;;
esac

echo ""
echo "=============================================================================="
echo "Next steps:"
echo "  1. Place your PDF file in this directory"
echo "  2. Run: python3 test_extractor.py"
echo "  3. Or: python3 example_usage.py"
echo "=============================================================================="
echo ""
