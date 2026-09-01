import type { NextRequest } from "next/server";

const BACKEND_INTERNAL_URL =
  process.env.BACKEND_INTERNAL_URL ?? "http://127.0.0.1:8000";

const REQUEST_HEADERS = [
  "range",
  "if-range",
  "if-none-match",
  "if-modified-since"
] as const;

const RESPONSE_HEADERS = [
  "accept-ranges",
  "cache-control",
  "content-disposition",
  "content-length",
  "content-range",
  "content-type",
  "etag",
  "last-modified"
] as const;

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

function backendPath(path: string[]): string[] {
  if (path.length === 3 && path[0] === "exports" && path[2] === "video.mp4") {
    return [path[0], path[1], "download"];
  }
  if (path.length === 3 && path[0] === "jobs" && path[2] === "archive.zip") {
    return [path[0], path[1], "download.zip"];
  }
  return path;
}

async function proxyBackendAsset(
  request: NextRequest,
  context: RouteContext
): Promise<Response> {
  const { path } = await context.params;
  if (path.length === 0 || path.some((segment) => !segment || segment === "." || segment === "..")) {
    return new Response("Invalid backend path", { status: 400 });
  }

  const encodedPath = backendPath(path)
    .map((segment) => encodeURIComponent(segment))
    .join("/");
  const target = new URL(`/api/${encodedPath}`, BACKEND_INTERNAL_URL);
  target.search = request.nextUrl.search;

  const requestHeaders = new Headers();
  for (const name of REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) {
      requestHeaders.set(name, value);
    }
  }
  if (request.method === "HEAD") {
    requestHeaders.set("range", "bytes=0-0");
  }

  const backendResponse = await fetch(target, {
    method: request.method === "HEAD" ? "GET" : request.method,
    headers: requestHeaders,
    cache: "no-store",
    redirect: "manual"
  });
  const responseHeaders = new Headers();
  for (const name of RESPONSE_HEADERS) {
    const value = backendResponse.headers.get(name);
    if (value) {
      responseHeaders.set(name, value);
    }
  }

  let responseStatus = backendResponse.status;
  if (request.method === "HEAD") {
    const contentRange = responseHeaders.get("content-range");
    const totalSize = contentRange?.match(/\/(\d+)$/)?.[1];
    if (backendResponse.status === 206 && totalSize) {
      responseHeaders.set("content-length", totalSize);
      responseHeaders.delete("content-range");
      responseStatus = 200;
    }
    await backendResponse.arrayBuffer();
  }

  return new Response(request.method === "HEAD" ? null : backendResponse.body, {
    status: responseStatus,
    headers: responseHeaders
  });
}

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxyBackendAsset(request, context);
}

export async function HEAD(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxyBackendAsset(request, context);
}
