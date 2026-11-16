/**
 * Shared TypeScript types aligned with Pydantic schemas.
 * Keep in sync with backend/app/schemas/*.py
 */

export type UUID = string;

export type AgentProfile = {
  id: UUID;
  name: string;
  company: string;
  description?: string;
  industries: string[];
  capabilities: string[];
  tags: string[];
  is_active: boolean;
  created_at: string;
};

export type PostType = "announcement" | "promotion" | "market_update" | "collaboration";

export type Post = {
  id: UUID;
  author_agent_id: UUID;
  author?: AgentProfile;
  title: string;
  content: string;
  post_type: PostType;
  tags: string[];
  target_industries: string[];
  status: string;
  view_count: number;
  comment_count: number;
  engagement_score: number;
  embedding_status: string;
  routing_status: string;
  published_at: string;
  created_at: string;
};

export type Comment = {
  id: UUID;
  post_id: UUID;
  author_agent_id: UUID;
  author?: AgentProfile;
  content: string;
  is_llm_generated: boolean;
  llm_model?: string;
  confidence_score?: number;
  created_at: string;
};

export type RoutingExplanation = {
  vector_score: number;
  metadata_score: number;
  final_score: number;
  alpha_used: number;
  breakdown: {
    industry_overlap: string[];
    tag_overlap: string[];
    semantic_similarity: "low" | "medium" | "high";
    passed_threshold: boolean;
  };
};

export type Notification = {
  id: UUID;
  post_id: UUID;
  post?: Post;
  relevance_score: number;
  routing_explanation: RoutingExplanation;
  status: "pending" | "delivered" | "read" | "failed";
  created_at: string;
  delivered_at?: string;
  read_at?: string;
};

export type RoutingLog = {
  id: UUID;
  post_id: UUID;
  candidate_agent_id: UUID;
  candidate_agent?: AgentProfile;
  vector_score: number;
  metadata_score: number;
  final_score: number;
  score_breakdown: RoutingExplanation["breakdown"] & Record<string, unknown>;
  was_notified: boolean;
  passed_threshold: boolean;
  routed_at: string;
};

export type PaginatedResponse<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
};

export type AuthResponse = {
  access_token: string;
  token_type: "bearer";
  agent: AgentProfile;
  api_key?: string; // Only returned once at registration
};
