import os
import sys
import runpy

real_app_dir = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..", "GeneLink", "genelink-audit", "artifacts", "api-server"
    )
)

os.chdir(real_app_dir)
sys.path.insert(0, real_app_dir)

runpy.run_path(os.path.join(real_app_dir, "app.py"), run_name="__main__")
