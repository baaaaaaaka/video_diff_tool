"""Dependency manager to check and install requirements."""

import sys
import subprocess
import importlib.metadata
import pkg_resources
from pathlib import Path
from typing import List, Tuple

class DependencyManager:
    """Manages application dependencies."""
    
    def __init__(self, requirements_path: Path):
        self.requirements_path = requirements_path
    
    def check_dependencies(self) -> Tuple[List[str], List[str]]:
        """
        Check which dependencies are satisfied and which are missing.
        Returns: (missing_packages, installed_packages)
        """
        if not self.requirements_path.exists():
            print(f"Warning: Requirements file not found at {self.requirements_path}")
            return [], []

        missing = []
        installed = []
        
        with open(self.requirements_path, 'r') as f:
            requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
        for req in requirements:
            try:
                # Parse requirement (e.g. "PyQt6>=6.5.0" -> "PyQt6")
                # Using pkg_resources to parse complex requirements safely
                parsed_req = list(pkg_resources.parse_requirements(req))[0]
                package_name = parsed_req.project_name
                
                try:
                    dist = pkg_resources.get_distribution(package_name)
                    # Check version if specified
                    if parsed_req.specs:
                        if not parsed_req.__contains__(dist):
                            missing.append(req)
                        else:
                            installed.append(req)
                    else:
                        installed.append(req)
                except pkg_resources.DistributionNotFound:
                    missing.append(req)
                    
            except Exception as e:
                print(f"Error checking requirement '{req}': {e}")
                # Fallback to simple check if pkg_resources fails
                package_name = req.split('>')[0].split('<')[0].split('=')[0]
                try:
                    importlib.metadata.version(package_name)
                    installed.append(req)
                except importlib.metadata.PackageNotFoundError:
                    missing.append(req)

        return missing, installed

    def install_packages(self, packages: List[str]) -> bool:
        """Install list of packages using pip."""
        if not packages:
            return True
            
        print(f"Installing missing dependencies: {', '.join(packages)}...")
        
        try:
            # Use the current python executable to ensure we install in the right environment
            cmd = [sys.executable, "-m", "pip", "install"] + packages
            subprocess.check_call(cmd)
            print("Dependencies installed successfully.")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to install dependencies. Error: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error during installation: {e}")
            return False

def check_and_install_dependencies():
    """Main entry point to check and install dependencies."""
    # Locate requirements.txt relative to this file (assuming it's in src/ or parent)
    # Current structure: src/dependency_manager.py
    # Requirements: ../requirements.txt
    
    current_dir = Path(__file__).parent
    project_root = current_dir.parent
    req_file = project_root / "requirements.txt"
    
    if not req_file.exists():
        # Try looking in current working directory
        req_file = Path("requirements.txt")
    
    if req_file.exists():
        manager = DependencyManager(req_file)
        missing, _ = manager.check_dependencies()
        
        if missing:
            print(f"Missing dependencies detected: {missing}")
            print("Attempting to auto-install...")
            if manager.install_packages(missing):
                print("Please restart the application to ensure all changes take effect.")
                # In many cases, simple imports might work, but for complex packages like PyQt,
                # a restart is safer. However, we can try to continue.
            else:
                print("Could not install dependencies. Application may fail to start.")
                input("Press Enter to exit...")
                sys.exit(1)
    else:
        print("Warning: requirements.txt not found. Skipping dependency check.")

