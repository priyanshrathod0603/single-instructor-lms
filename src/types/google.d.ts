// Google Identity Services (GSI) TypeScript Definitions
// Reference: https://developers.google.com/identity/gsi/web/reference/js-reference

export interface GoogleCredentialResponse {
  credential?: string;
  select_by?: string;
}

export interface PromptMomentNotification {
  isDisplayed: () => boolean;
  isNotDisplayed: () => boolean;
  getNotDisplayedReason: () => string;
  isSkippedMoment: () => boolean;
  getSkippedReason: () => string;
  isDismissedMoment: () => boolean;
  getDismissedReason: () => string;
  getMomentType: () => string;
}

export interface IdConfiguration {
  client_id: string;
  callback: (response: GoogleCredentialResponse) => void;
  auto_select?: boolean;
  cancel_on_tap_outside?: boolean;
  context?: string;
  prompt_parent_id?: string;
  state_cookie_domain?: string;
  ux_mode?: "popup" | "redirect";
  login_uri?: string;
  native_login_uri?: string;
  intermediate_iframe_close_callback?: () => void;
  use_fedcm_for_prompt?: boolean;
}

export interface GsiButtonConfiguration {
  type?: "standard" | "icon";
  theme?: "outline" | "filled_blue" | "filled_black";
  size?: "large" | "medium" | "small";
  text?: "signin_with" | "signup_with" | "continue_with" | "signin";
  shape?: "rectangular" | "pill" | "circle" | "square";
  logo_alignment?: "left" | "center";
  width?: number | string;
  locale?: string;
  click_listener?: () => void;
}

declare global {
  interface Window {
    google?: {
      accounts?: {
        id?: {
          initialize: (config: IdConfiguration) => void;
          prompt: (momentListener?: (notification: PromptMomentNotification) => void) => void;
          renderButton: (parent: HTMLElement, options: GsiButtonConfiguration) => void;
          disableAutoSelect: () => void;
          storeCredential: (credential: unknown, callback?: () => void) => void;
          cancel: () => void;
        };
      };
    };
  }
}
