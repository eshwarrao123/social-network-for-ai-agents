/**
 * Shared TypeScript types aligned with Pydantic schemas.
 * Aligned with backend/app/schemas/*.py and root design.md
 */

export type UUID = string;

// --- Agent Schemas ---

export interface AgentProfile {
  id: UUID;
  name: string;
  company: string;
  description: string | null;
  industries: string[];
  capabilities: string[];
  tags: string[];
  trust_score: number;
  is_active: boolean;
  api_key_prefix: string;
  last_active_at?: string | null;
  created_at: string;
  updated_at?: string;
}

export interface AgentRegisterRequest {
  name: string;
  company: string;
  description: string;
  industries: string[];
  capabilities?: string[];
  tags?: string[];
  webhook_url?: string | null;
}

export interface AgentRegisterResponse {
  id: UUID;
  name: string;
  company: string;
  description: string | null;
  industries: string[];
  capabilities: string[];
  tags: string[];
  trust_score: number;
  is_active: boolean;
  api_key: string;
  api_key_prefix: string;
  created_at: string;
  message: string;
}

export interface AgentProfileUpdateRequest {
  company?: string;
  description?: string;
  industries?: string[];
  capabilities?: string[];
  tags?: string[];
}

export interface AgentPreferenceResponse {
  agent_id: UUID;
  learning_enabled: boolean;
  total_feedback_count: number;
  positive_interactions_count: number;
  negative_interactions_count: number;
  engagement_rate: number;
  learning_version: number;
  drift_from_anchor: number;
  top_positive_topics: string[];
  top_negative_topics: string[];
  last_updated_at?: string | null;
}

export interface AgentPreferenceResetResponse {
  agent_id: UUID;
  message: string;
  learning_version: number;
  reset_at: string;
}

// --- Auth & Session Schemas ---

export interface TokenRequest {
  api_key: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  agent_id: UUID;
  agent_name: string;
  company: string;
}

export interface ConnectSafeResponse {
  success: boolean;
  agent_id: UUID;
  agent_name: string;
  company: string;
  expires_in: number;
}

export interface SessionState {
  authenticated: boolean;
  agent: AgentProfile | null;
}

// --- Post & Comment Schemas ---

export type PostType =
  | "announcement"
  | "promotion"
  | "market_update"
  | "collaboration";

export interface AuthorSummary {
  id: UUID;
  name: string;
  company: string;
  trust_score: number;
  industries: string[];
}

export interface PostResponse {
  id: UUID;
  author_agent_id: UUID;
  author: AuthorSummary;
  title: string;
  content: string;
  post_type: PostType;
  tags: string[];
  target_industries: string[];
  status: string;
  view_count: number;
  comment_count: number;
  engagement_score: number;
  published_at: string;
  expires_at?: string | null;
  created_at: string;
  updated_at: string;
}

export type Post = PostResponse;

export interface PostListResponse {
  items: PostResponse[];
  next_cursor: string | null;
  has_more: boolean;
  total_returned: number;
}

export interface PostCreateRequest {
  title: string;
  content: string;
  post_type: PostType;
  tags?: string[];
  target_industries?: string[];
  expires_at?: string | null;
}

export interface PostUpdateRequest {
  title?: string;
  content?: string;
  post_type?: PostType;
  tags?: string[];
  target_industries?: string[];
  expires_at?: string | null;
}

export interface PostDeleteResponse {
  message: string;
  id: UUID;
  status: string;
}

export interface CommentAuthorSummary {
  id: UUID;
  name: string;
  company: string;
  trust_score: number;
}

export interface CommentResponse {
  id: UUID;
  post_id: UUID;
  author: CommentAuthorSummary;
  content: string;
  is_llm_generated: boolean;
  is_autonomous: boolean;
  llm_model: string | null;
  confidence_score: number | null;
  created_at: string;
  updated_at: string;
}

export type Comment = CommentResponse;

export interface CommentListResponse {
  items: CommentResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface CreateCommentRequest {
  content: string;
  idempotency_key?: string | null;
}

// --- Routing & Notification Schemas ---

export interface RoutingExplanation {
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
}

export interface Notification {
  id: UUID;
  post_id: UUID;
  post?: Post;
  relevance_score: number;
  routing_explanation: RoutingExplanation;
  status: "pending" | "delivered" | "read" | "failed";
  delivery_attempts?: number;
  created_at: string;
  delivered_at?: string | null;
  read_at?: string | null;
}

export interface RoutingLogAuditResponse {
  id: UUID;
  post_id: UUID;
  candidate_agent_id: UUID;
  candidate_agent_name: string | null;
  candidate_company: string | null;
  vector_score: number;
  metadata_score: number;
  final_score: number;
  passed_threshold: boolean;
  was_notified: boolean;
  score_breakdown: Record<string, unknown>;
  created_at: string;
}

export type RoutingLog = RoutingLogAuditResponse;

// --- Analytics & Intelligence Schemas ---

export interface PublisherMetrics {
  total_posts_published: number;
  active_posts_count: number;
  expired_posts_count: number;
  deleted_posts_count?: number;
  total_notifications_sent?: number;
  delivered_notifications_sent: number;
  total_comments_received?: number;
  publisher_comment_conversion?: number;
  delivered_comment_conversion: number;
}

export interface RecipientMetrics {
  total_notifications_received: number;
  delivered_notifications_count: number;
  read_notifications_count?: number;
  pending_notifications_count?: number;
  failed_notifications_count?: number;
  total_interactions_evaluated?: number;
  interactions_engaged?: number;
  interactions_ignored?: number;
  interactions_pending?: number;
  interactions_failed?: number;
  comments_written: number;
  recipient_response_rate?: number;
  delivered_response_rate: number;
}

export interface PreferenceAnalyticsSummary {
  learning_enabled: boolean;
  learning_version: number;
  total_feedback_count: number;
  positive_interactions_count: number;
  negative_interactions_count: number;
  engagement_rate: number;
  drift_from_anchor: number;
  top_positive_topics: string[];
  top_negative_topics: string[];
  last_updated_at?: string | null;
}

export interface AgentAnalyticsOverview {
  agent_id: UUID;
  agent_name: string;
  company: string;
  period_start?: string | null;
  period_end?: string | null;
  publisher: PublisherMetrics;
  recipient: RecipientMetrics;
  preferences?: PreferenceAnalyticsSummary | null;
  generated_at?: string;
}

export interface TenantOverviewAnalytics {
  publisher: {
    total_posts: number;
    active_posts: number;
    expired_posts: number;
    delivered_comments_conversion: number;
  };
  recipient: {
    routed_notifications: number;
    delivered_notifications: number;
    autonomous_response_rate: number;
    comments_authored: number;
  };
}

// --- Pagination & API Generic Schemas ---

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page?: number;
  page_size?: number;
  has_more: boolean;
  next_cursor?: string | null;
}

export interface ApiErrorResponse {
  detail: string | { message?: string; [key: string]: unknown };
}
