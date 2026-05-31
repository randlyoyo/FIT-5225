import zipfile, os

base = "aws-lambdas"
os.makedirs(f"{base}/lambdas", exist_ok=True)

for handler in ["api_handler", "process_handler"]:
    zip_path = f"{base}/lambdas/{handler}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(f"{base}/{handler}/lambda_function.py", "lambda_function.py")
        for root, dirs, files in os.walk(f"{base}/shared"):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, base))
    size = os.path.getsize(zip_path)
    print(f"  {handler}.zip: {size} bytes")

# Layer zip
lp = f"{base}/lambdas/layer.zip"
if os.path.exists(lp):
    os.remove(lp)
with zipfile.ZipFile(lp, "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(f"{base}/layer"):
        for f in files:
            p = os.path.join(root, f)
            z.write(p, os.path.relpath(p, base))
size = os.path.getsize(lp)
print(f"  layer.zip: {size} bytes")

print("Done — all zip files ready.")
