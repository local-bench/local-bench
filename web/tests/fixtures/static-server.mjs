import { createReadStream, statSync } from "node:fs";
import { createServer } from "node:http";
import { join, normalize } from "node:path";

const root = process.argv[2];
const port = Number(process.argv[3]);
createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url ?? "/", "http://localhost").pathname);
  let file = join(root, normalize(pathname).replace(/^[/\\]+/, ""));
  try {
    if (statSync(file).isDirectory()) file = join(file, "index.html");
    response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    createReadStream(file).pipe(response);
  } catch {
    response.writeHead(404).end("not found");
  }
}).listen(port, "127.0.0.1");
