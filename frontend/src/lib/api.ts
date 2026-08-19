const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE_URL) {
    throw new ApiError(
      "NEXT_PUBLIC_API_BASE_URL is not configured for this deployment.",
    );
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError("Could not reach the Veritas API. Is it running?");
  }
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new ApiError(detail || `Request failed (${response.status})`, response.status);
  }
  return response.json() as Promise<T>;
}

export interface HealthResponse {
  status: "healthy" | "unhealthy";
  database: "ok" | "failed";
  redis: "ok" | "failed";
  version: string;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export interface SearchResult {
  chunk_id: string;
  document_id: string;
  content: string;
  score: number;
  bm25_rank: number | null;
  dense_rank: number | null;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
}

export function search(query: string): Promise<SearchResponse> {
  return request<SearchResponse>(`/search?q=${encodeURIComponent(query)}`);
}

export interface Citation {
  chunk_id: string;
  similarity: number;
}

export interface AskResponse {
  answer: string | null;
  citations: Citation[];
  confidence: number;
  refused: boolean;
  latency_ms: number;
}

export function ask(question: string): Promise<AskResponse> {
  return request<AskResponse>("/ask", {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}
