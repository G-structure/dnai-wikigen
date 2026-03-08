#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# quickstart.sh — "it just works" dependency bootstrap for dnai-wikigen
#
# Installs everything needed to build the Attested Diligence Room:
#   git, curl, jq, poppler, orbstack (macOS) / docker (linux), node,
#   foundry, rust, phala cloud cli
#
# Idempotent: safe to run multiple times. Skips what's already installed.
# Tested on: macOS 26.3 Tahoe (Darwin 25.3.0, arm64)
# Should work: macOS (arm64/x86_64), Linux (Debian/Ubuntu, Fedora/RHEL, Arch)
# ============================================================================

# --- Colors & helpers -------------------------------------------------------

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { printf "${BLUE}[info]${NC}  %s\n" "$*"; }
ok()      { printf "${GREEN}[ok]${NC}    %s\n" "$*"; }
warn()    { printf "${YELLOW}[skip]${NC}  %s\n" "$*"; }
err()     { printf "${RED}[err]${NC}   %s\n" "$*" >&2; }
section() { printf "\n${BOLD}${CYAN}── %s ──${NC}\n" "$*"; }

has() { command -v "$1" &>/dev/null; }

# Track results for final summary
INSTALLED=()
SKIPPED=()
FAILED=()
MANUAL=()

mark_installed() { INSTALLED+=("$1"); }
mark_skipped()   { SKIPPED+=("$1"); }
mark_failed()    { FAILED+=("$1"); }
mark_manual()    { MANUAL+=("$1"); }

# --- Detect platform -------------------------------------------------------

OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Darwin) PLATFORM="macos" ;;
  Linux)  PLATFORM="linux" ;;
  *)      err "Unsupported OS: $OS"; exit 1 ;;
esac

# Detect Linux distro family
DISTRO=""
if [ "$PLATFORM" = "linux" ]; then
  if [ -f /etc/os-release ]; then
    . /etc/os-release
    case "$ID" in
      ubuntu|debian|pop|mint|elementary|zorin) DISTRO="debian" ;;
      fedora|rhel|centos|rocky|alma|ol)        DISTRO="fedora" ;;
      arch|manjaro|endeavouros)                 DISTRO="arch" ;;
      *)
        # Try ID_LIKE as fallback
        case "${ID_LIKE:-}" in
          *debian*|*ubuntu*) DISTRO="debian" ;;
          *fedora*|*rhel*)   DISTRO="fedora" ;;
          *arch*)            DISTRO="arch" ;;
          *)                 DISTRO="unknown" ;;
        esac
        ;;
    esac
  else
    DISTRO="unknown"
  fi
fi

section "Platform"
info "OS: $OS | Arch: $ARCH | Platform: $PLATFORM${DISTRO:+ | Distro: $DISTRO}"

# --- Helper: install system packages ----------------------------------------

pkg_install() {
  local pkg="$1"
  if [ "$PLATFORM" = "macos" ]; then
    brew install "$pkg"
  elif [ "$DISTRO" = "debian" ]; then
    sudo apt-get update -qq && sudo apt-get install -y -qq "$pkg"
  elif [ "$DISTRO" = "fedora" ]; then
    sudo dnf install -y -q "$pkg"
  elif [ "$DISTRO" = "arch" ]; then
    sudo pacman -S --noconfirm --needed "$pkg"
  else
    err "Cannot auto-install '$pkg' on this distro. Install it manually."
    mark_failed "$pkg"
    return 1
  fi
}

# --- Homebrew (macOS only) --------------------------------------------------

if [ "$PLATFORM" = "macos" ]; then
  section "Homebrew"
  if has brew; then
    ok "Homebrew already installed"
    mark_skipped "homebrew"
  else
    info "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add to PATH for this session
    if [ "$ARCH" = "arm64" ]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
    else
      eval "$(/usr/local/bin/brew shellenv)"
    fi
    ok "Homebrew installed"
    mark_installed "homebrew"
  fi
fi

# --- Git --------------------------------------------------------------------

section "Git"
if has git; then
  ok "git $(git --version | awk '{print $3}')"
  mark_skipped "git"
else
  info "Installing git..."
  pkg_install git
  ok "git installed"
  mark_installed "git"
fi

# --- curl -------------------------------------------------------------------

section "curl"
if has curl; then
  ok "curl available"
  mark_skipped "curl"
else
  info "Installing curl..."
  pkg_install curl
  ok "curl installed"
  mark_installed "curl"
fi

# --- jq --------------------------------------------------------------------

section "jq"
if has jq; then
  ok "jq available"
  mark_skipped "jq"
else
  info "Installing jq..."
  pkg_install jq
  ok "jq installed"
  mark_installed "jq"
fi

# --- poppler (PDF tools) ---------------------------------------------------

section "poppler"
if has pdftoppm; then
  ok "poppler available (pdftoppm)"
  mark_skipped "poppler"
else
  info "Installing poppler..."
  if [ "$PLATFORM" = "macos" ]; then
    pkg_install poppler
  elif [ "$DISTRO" = "debian" ]; then
    sudo apt-get update -qq && sudo apt-get install -y -qq poppler-utils
  elif [ "$DISTRO" = "fedora" ]; then
    sudo dnf install -y -q poppler-utils
  elif [ "$DISTRO" = "arch" ]; then
    sudo pacman -S --noconfirm --needed poppler
  else
    err "Install poppler manually"
    mark_failed "poppler"
  fi
  if has pdftoppm; then
    ok "poppler installed"
    mark_installed "poppler"
  fi
fi

# --- Container runtime (OrbStack on macOS, Docker on Linux) -----------------

if [ "$PLATFORM" = "macos" ]; then
  section "OrbStack (Docker runtime for macOS)"
  if has orb && has docker && docker info &>/dev/null; then
    ok "OrbStack running — docker CLI available"
    mark_skipped "orbstack"
  elif has orb; then
    warn "OrbStack installed but not running"
    info "Starting OrbStack..."
    open -a OrbStack 2>/dev/null || true
    for i in $(seq 1 15); do
      if docker info &>/dev/null; then break; fi
      sleep 2
    done
    if docker info &>/dev/null; then
      ok "OrbStack started — docker CLI available"
      mark_skipped "orbstack"
    else
      warn "OrbStack installed but daemon not ready. Open OrbStack manually."
      mark_manual "orbstack (start app)"
    fi
  else
    info "Installing OrbStack via Homebrew..."
    brew install --cask orbstack
    info "Launching OrbStack..."
    open -a OrbStack 2>/dev/null || true
    for i in $(seq 1 20); do
      if has docker && docker info &>/dev/null; then break; fi
      sleep 2
    done
    if has docker && docker info &>/dev/null; then
      ok "OrbStack installed and running"
      mark_installed "orbstack"
    else
      ok "OrbStack installed — open OrbStack to finish setup"
      mark_installed "orbstack"
      mark_manual "orbstack (open app to complete first-run)"
    fi
  fi
else
  section "Docker"
  if has docker && docker info &>/dev/null; then
    ok "Docker $(docker --version | awk '{print $3}' | tr -d ',')"
    mark_skipped "docker"
  elif has docker; then
    warn "Docker CLI found but daemon not running"
    info "Try: sudo systemctl start docker"
    mark_manual "docker (start daemon)"
  else
    info "Installing Docker..."
    if [ "$DISTRO" = "debian" ] || [ "$DISTRO" = "fedora" ]; then
      info "Using Docker's official install script..."
      curl -fsSL https://get.docker.com | sh
      sudo systemctl enable --now docker 2>/dev/null || true
      if ! groups | grep -q docker; then
        sudo usermod -aG docker "$USER"
        warn "Added $USER to docker group. Log out and back in, or run: newgrp docker"
      fi
      mark_installed "docker"
    elif [ "$DISTRO" = "arch" ]; then
      sudo pacman -S --noconfirm --needed docker
      sudo systemctl enable --now docker
      if ! groups | grep -q docker; then
        sudo usermod -aG docker "$USER"
        warn "Added $USER to docker group. Log out and back in, or run: newgrp docker"
      fi
      mark_installed "docker"
    else
      err "Install Docker manually: https://docs.docker.com/get-docker/"
      mark_failed "docker"
    fi
  fi

  section "Docker Compose"
  if docker compose version &>/dev/null 2>&1; then
    ok "Docker Compose $(docker compose version --short 2>/dev/null || echo 'available')"
    mark_skipped "docker-compose"
  elif has docker-compose; then
    ok "docker-compose (standalone) available"
    mark_skipped "docker-compose"
  elif [ "$DISTRO" = "debian" ]; then
    info "Installing docker-compose-plugin..."
    sudo apt-get install -y -qq docker-compose-plugin 2>/dev/null || true
    mark_installed "docker-compose"
  elif [ "$DISTRO" = "fedora" ]; then
    sudo dnf install -y -q docker-compose-plugin 2>/dev/null || true
    mark_installed "docker-compose"
  else
    warn "Install docker compose plugin manually"
    mark_manual "docker-compose"
  fi
fi

# --- Node.js ----------------------------------------------------------------

section "Node.js"
NODE_MIN=18
if has node; then
  NODE_VER="$(node -v | tr -d 'v' | cut -d. -f1)"
  if [ "$NODE_VER" -ge "$NODE_MIN" ]; then
    ok "Node.js $(node -v)"
    mark_skipped "node"
  else
    warn "Node.js $(node -v) found but v${NODE_MIN}+ required"
    info "Installing latest LTS via nvm..."
    export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    if [ ! -s "$NVM_DIR/nvm.sh" ]; then
      curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
    fi
    # shellcheck source=/dev/null
    . "$NVM_DIR/nvm.sh"
    nvm install --lts
    nvm use --lts
    ok "Node.js $(node -v) installed via nvm"
    mark_installed "node"
  fi
else
  info "Installing Node.js..."
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  if [ ! -s "$NVM_DIR/nvm.sh" ]; then
    info "Installing nvm first..."
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
  fi
  # shellcheck source=/dev/null
  . "$NVM_DIR/nvm.sh"
  nvm install --lts
  nvm use --lts
  ok "Node.js $(node -v) installed via nvm"
  mark_installed "node"
fi

# --- npm (sanity check) -----------------------------------------------------

if ! has npm; then
  warn "npm not found — should come with Node.js. Check your PATH."
  mark_manual "npm"
fi

# --- Foundry ----------------------------------------------------------------

section "Foundry (forge, cast, anvil)"
if has forge; then
  ok "Foundry already installed — forge $(forge --version 2>/dev/null | head -1 | awk '{print $2}' || echo 'available')"
  mark_skipped "foundry"
else
  info "Installing Foundry via foundryup..."
  export FOUNDRY_DIR="${FOUNDRY_DIR:-$HOME/.foundry}"
  curl -fsSL https://foundry.paradigm.xyz | bash
  # Source the env so foundryup is on PATH
  export PATH="$FOUNDRY_DIR/bin:$PATH"
  foundryup
  ok "Foundry installed — forge, cast, anvil, chisel"
  mark_installed "foundry"
fi

# Verify individual tools
for tool in forge cast anvil; do
  if has "$tool"; then
    ok "  $tool available"
  else
    # Try with explicit path
    if [ -x "$HOME/.foundry/bin/$tool" ]; then
      ok "  $tool available at ~/.foundry/bin/$tool"
      info "  Add to PATH: export PATH=\"\$HOME/.foundry/bin:\$PATH\""
    else
      err "  $tool not found"
      mark_failed "$tool"
    fi
  fi
done

# --- Rust -------------------------------------------------------------------

section "Rust"
if has rustc; then
  ok "Rust $(rustc --version | awk '{print $2}')"
  mark_skipped "rust"
else
  info "Installing Rust via rustup..."
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
  # shellcheck source=/dev/null
  . "$HOME/.cargo/env"
  ok "Rust $(rustc --version | awk '{print $2}') installed"
  mark_installed "rust"
fi

# --- Phala Cloud CLI --------------------------------------------------------

section "Phala Cloud CLI"
if has phala; then
  ok "Phala CLI available"
  mark_skipped "phala-cli"
elif npm list -g @aspect-build/phala 2>/dev/null | grep -q phala 2>/dev/null; then
  ok "Phala CLI available (global npm)"
  mark_skipped "phala-cli"
else
  info "Installing Phala Cloud CLI..."
  if has npm; then
    npm install -g @phala/cloud-cli 2>/dev/null && {
      ok "Phala Cloud CLI installed"
      mark_installed "phala-cli"
    } || {
      # Try alternate package name
      npm install -g phala 2>/dev/null && {
        ok "Phala CLI installed"
        mark_installed "phala-cli"
      } || {
        warn "Could not auto-install Phala CLI. Check: https://docs.phala.com/phala-cloud/phala-cloud-cli/start-from-cloud-cli"
        mark_manual "phala-cli"
      }
    }
  else
    warn "npm not available — cannot install Phala CLI"
    mark_manual "phala-cli"
  fi
fi

# --- Git submodules ---------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

section "Git Submodules"
if [ -f "$SCRIPT_DIR/.gitmodules" ]; then
  info "Initializing and updating submodules..."
  cd "$SCRIPT_DIR"
  git submodule update --init --recursive
  ok "Submodules ready"
  mark_installed "submodules"
else
  warn "No .gitmodules found — skipping"
  mark_skipped "submodules"
fi

# --- .env scaffold ----------------------------------------------------------

section "Environment File"
if [ -f "$SCRIPT_DIR/.env" ] && [ -s "$SCRIPT_DIR/.env" ]; then
  ok ".env exists and is non-empty"
  mark_skipped ".env"
else
  if [ -f "$SCRIPT_DIR/example.env" ] && [ -s "$SCRIPT_DIR/example.env" ]; then
    info "Copying example.env -> .env"
    cp "$SCRIPT_DIR/example.env" "$SCRIPT_DIR/.env"
    ok ".env created from example.env — fill in your secrets"
    mark_installed ".env"
  else
    warn ".env is empty and example.env has no template yet"
    mark_skipped ".env"
  fi
fi

# --- Summary ----------------------------------------------------------------

section "Summary"

if [ ${#INSTALLED[@]} -gt 0 ]; then
  printf "${GREEN}Installed:${NC} %s\n" "$(IFS=', '; echo "${INSTALLED[*]}")"
fi

if [ ${#SKIPPED[@]} -gt 0 ]; then
  printf "${BLUE}Already OK:${NC} %s\n" "$(IFS=', '; echo "${SKIPPED[*]}")"
fi

if [ ${#MANUAL[@]} -gt 0 ]; then
  printf "${YELLOW}Needs manual action:${NC}\n"
  for item in "${MANUAL[@]}"; do
    printf "  - %s\n" "$item"
  done
fi

if [ ${#FAILED[@]} -gt 0 ]; then
  printf "${RED}Failed:${NC} %s\n" "$(IFS=', '; echo "${FAILED[*]}")"
fi

echo ""
if [ ${#FAILED[@]} -eq 0 ] && [ ${#MANUAL[@]} -eq 0 ]; then
  printf "${GREEN}${BOLD}All dependencies ready. Let's build.${NC}\n"
else
  printf "${YELLOW}${BOLD}Almost there — resolve the items above and re-run this script.${NC}\n"
fi

# --- PATH reminder ----------------------------------------------------------

echo ""
info "If any tools aren't on your PATH, add these to your shell profile:"
echo '  export PATH="$HOME/.foundry/bin:$PATH"'
echo '  export PATH="$HOME/.cargo/bin:$PATH"'
echo '  [ -s "$HOME/.nvm/nvm.sh" ] && . "$HOME/.nvm/nvm.sh"'
echo ""
