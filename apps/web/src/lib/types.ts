export type User = {
  id: string;
  email: string;
  display_name: string;
  timezone: string;
  role: "owner" | "member";
  mfa_enabled: boolean;
  created_at: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  csrf_token: string;
  user: User;
};

export type SessionInfo = {
  id: string;
  user_agent: string | null;
  ip: string | null;
  created_at: string;
  last_used_at: string;
  current: boolean;
};

export type MfaSetup = { secret: string; otpauth_uri: string };
