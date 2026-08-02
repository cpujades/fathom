import type {
  BriefingListItem,
  BriefingListResponse,
  BriefingListSort,
  BriefingSourceFilter
} from "@fathom/api-client";

export type { BriefingListItem, BriefingListResponse, BriefingListSort, BriefingSourceFilter };

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
