export const ASSISTANT_PROFILE_EVENT = "assistant-profile-updated"
export const DEFAULT_AI_NICKNAME = "哈基米"
export const DEFAULT_USER_NICKNAME = "大王"
export const DEFAULT_AI_AVATAR = "/robot-avatar.jpg"

export interface AssistantProfile {
  aiNickname: string
  userNickname: string
  aiAvatar: string
}

export function resolveAssistantAvatar(value: unknown) {
  var avatar = String(value || "").trim()
  if (!avatar || avatar === "cat_icon.png") return DEFAULT_AI_AVATAR
  if (avatar.startsWith("data:") || avatar.startsWith("http://") || avatar.startsWith("https://") || avatar.startsWith("/")) return avatar
  return "/" + avatar
}

export function normalizeAssistantProfile(cfg: any): AssistantProfile {
  return {
    aiNickname: String(cfg?.aiNickname || cfg?.ai_nickname || DEFAULT_AI_NICKNAME).trim() || DEFAULT_AI_NICKNAME,
    userNickname: String(cfg?.userNickname || cfg?.user_nickname || DEFAULT_USER_NICKNAME).trim() || DEFAULT_USER_NICKNAME,
    aiAvatar: resolveAssistantAvatar(cfg?.aiAvatar || cfg?.ai_avatar),
  }
}
