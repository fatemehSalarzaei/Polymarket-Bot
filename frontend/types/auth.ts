export type User = {
  id: number;
  email: string;
  username: string;
  role: "super_user" | "admin" | "trader" | "viewer" | string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
};

export type LoginResponse = {
  ok: boolean;
  user: User;
  expires_in_minutes: number;
};

export type CurrentUser = {
  authenticated: boolean;
  user: User | null;
};
