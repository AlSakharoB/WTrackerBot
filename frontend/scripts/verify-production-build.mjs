import { readdir, readFile, stat } from "node:fs/promises";
import { extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = fileURLToPath(new URL("..", import.meta.url));
const distRoot = join(projectRoot, "dist");
const indexPath = join(distRoot, "index.html");

async function listFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = await Promise.all(
    entries.map((entry) => {
      const path = join(directory, entry.name);
      return entry.isDirectory() ? listFiles(path) : [path];
    }),
  );
  return files.flat();
}

const indexHtml = await readFile(indexPath, "utf8");
const files = await listFiles(distRoot);
const relativeFiles = files.map((path) => relative(distRoot, path));
const forbiddenExtensions = new Set([".map", ".ts", ".tsx", ".mts", ".cts", ".jsx"]);
const forbiddenFiles = relativeFiles.filter((path) =>
  forbiddenExtensions.has(extname(path)),
);
const scriptAssets = relativeFiles.filter(
  (path) => path.startsWith("assets/") && extname(path) === ".js",
);
const styleAssets = relativeFiles.filter(
  (path) => path.startsWith("assets/") && extname(path) === ".css",
);
const hashedAssetPattern = /-[A-Za-z0-9_-]{8,}\.(?:css|js)$/;
const oversizedAssets = [];

for (const path of files) {
  const file = await stat(path);
  if (file.size > 2 * 1024 * 1024) {
    oversizedAssets.push(`${relative(distRoot, path)} (${file.size} bytes)`);
  }
}

if (forbiddenFiles.length > 0) {
  throw new Error(`Production build contains source files: ${forbiddenFiles.join(", ")}`);
}
if (
  scriptAssets.length === 0
  || styleAssets.length === 0
  || ![...scriptAssets, ...styleAssets].every((path) => hashedAssetPattern.test(path))
  || !indexHtml.includes("/assets/")
) {
  throw new Error("Production index does not reference hashed JavaScript and CSS assets");
}
if (oversizedAssets.length > 0) {
  throw new Error(`Production assets exceed 2 MiB: ${oversizedAssets.join(", ")}`);
}

console.log(`Verified production frontend: ${relativeFiles.length} files, no source maps`);
