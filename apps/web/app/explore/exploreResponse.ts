export function isUnknownExploreTopicResponse(status: number, requestedTopic: string | undefined): boolean {
  return status === 422 && Boolean(requestedTopic);
}
