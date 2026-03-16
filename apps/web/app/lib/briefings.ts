export type BriefingListSort = "newest" | "oldest";
export type BriefingSourceFilter = "all" | "youtube" | "url";

export type BriefingListItem = {
  session_id: string;
  briefing_id: string;
  title: string;
  author: string | null;
  source_url: string;
  source_host: string;
  source_type: "youtube" | "url";
  created_at: string;
  source_duration_seconds: number | null;
  source_thumbnail_url: string | null;
  session_path: string;
};

export type BriefingListResponse = {
  items: BriefingListItem[];
  total_count: number;
  limit: number;
  offset: number;
  has_more: boolean;
  query: string | null;
  sort: BriefingListSort;
  source_type: BriefingSourceFilter;
};

export type BriefingsQueryOptions = {
  limit?: number;
  offset?: number;
  query?: string;
  sort?: BriefingListSort;
  sourceType?: BriefingSourceFilter;
};

export const DEFAULT_BRIEFINGS_LIMIT = 24;

export const DEFAULT_BRIEFINGS_QUERY: Required<BriefingsQueryOptions> = {
  limit: DEFAULT_BRIEFINGS_LIMIT,
  offset: 0,
  query: "",
  sort: "newest",
  sourceType: "all"
};
