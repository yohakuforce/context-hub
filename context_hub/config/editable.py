"""Editable configuration registry — single source of truth for the admin GUI.

Defines which settings the GUI can read/write, their Japanese labels and grouping,
which are secrets (masked on read), whether a restart is needed, and — crucially —
per-field guidance (なぜ必要 / 取得手順 / どう設定するか) so users never get stuck.

Values are persisted to the ``.env`` file (the same file pydantic-settings reads at
startup), so the GUI edits exactly what the CLI/`.env` workflow already uses.
Secrets are never returned in full — only a masked hint (last 4 chars).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values, set_key, unset_key

# Default location of the .env file (current working directory).
DEFAULT_ENV_PATH = Path(".env")

_MASK = "••••"


@dataclass(frozen=True)
class ConfigField:
    """One editable setting exposed to the admin GUI (labels/help in Japanese).

    Attributes:
        env:              The ``.env`` key (UPPER_SNAKE_CASE) read/written.
        label:            Japanese form label.
        group:            Japanese section heading.
        secret:           True ⇒ masked on read, treated as sensitive.
        kind:             ``text`` | ``int`` | ``select`` | ``bool``.
        options:          Allowed values when ``kind == "select"``.
        help:             Short Japanese hint shown under the field.
        restart_required: True ⇒ a server restart is needed to take effect.
        tag:              Short "when is this needed" badge (e.g. "Slack取り込み時").
        why:              なぜこの設定が必要か.
        steps:            取得手順 (ordered).
        how_to_set:       この欄への入れ方.
    """

    env: str
    label: str
    group: str
    secret: bool = False
    kind: str = "text"
    options: tuple[str, ...] = ()
    help: str = ""
    restart_required: bool = False
    tag: str = ""
    why: str = ""
    steps: tuple[str, ...] = ()
    how_to_set: str = ""


# Registry — complete set of GUI-editable settings, in display order.
FIELDS: tuple[ConfigField, ...] = (
    # ------------------------------------------------------------------ App
    ConfigField(
        "APP_ENV", "動作環境", "アプリ", kind="select",
        options=("development", "production"), restart_required=True,
        help="ローカル運用は development。",
        tag="基本",
        why="development では管理画面の認証に DEV_API_KEY を使えます。production では "
            "DEV_API_KEY は無効になり、発行済みのコンシューマキー認証が必要になります。",
        steps=("個人のMac miniでのローカル運用なら development のままでOK。",),
        how_to_set="ローカル運用は development を選択。",
    ),
    ConfigField(
        "LOG_LEVEL", "ログ詳細度", "アプリ", kind="select",
        options=("DEBUG", "INFO", "WARNING", "ERROR"), restart_required=True,
        help="通常は INFO。", why="サーバが出すログの細かさです。",
        how_to_set="困ったとき以外は INFO で十分。",
    ),
    ConfigField(
        "SECRET_KEY", "シークレットキー", "アプリ", secret=True, restart_required=True,
        tag="本番は必須",
        why="アプリの署名等に使う秘密鍵です。既定の開発用のままにしないでください。",
        steps=("ターミナルで openssl rand -hex 32 を実行し、出力をコピー。",),
        how_to_set="「変更」を押してコピーした値を貼り付け → 保存。",
    ),
    # ------------------------------------------------------------- Database
    ConfigField(
        "CH_PROFILE", "プロファイル", "データベース", kind="select",
        options=("quickstart", "personal", "production"), restart_required=True,
        help="個人運用の目安は personal。",
        tag="基本",
        why="動作プリセットです。quickstart=SQLite+簡易埋め込み（最短）／personal=SQLite+"
            "bge-m3（日常運用）／production=PostgreSQL（複数人・本番）。",
        steps=(
            "変更したら context-hub migrate を実行してスキーマを適用。",
            "その後サーバを再起動。",
        ),
        how_to_set="Mac mini の個人運用なら personal が目安。",
    ),
    ConfigField(
        "DATABASE_URL", "データベースURL", "データベース", secret=True,
        restart_required=True,
        tag="本番(PostgreSQL)時",
        why="ドキュメント等の保存先DBです。quickstart/personal は SQLite（既定）なので "
            "通常この欄は触りません。production のみ PostgreSQL を指定します。",
        steps=(
            "SQLite（既定）: sqlite+aiosqlite:///./data/context_hub.db",
            "PostgreSQL: postgresql+asyncpg://〈ユーザー〉:〈パス〉@〈ホスト〉/〈DB名〉",
            "PostgreSQL を使うには pip install 'yohakuforce-context-hub[postgres]'。",
        ),
        how_to_set="SQLite運用ならそのままでOK。PostgreSQL なら「変更」で URL を貼り付け、"
                   "プロファイルも production にする。",
    ),
    # ------------------------------------------------------------------ LLM
    ConfigField(
        "LLM_PROVIDER", "AIプロバイダ", "AI（議事録→タスク抽出）", kind="select",
        options=("mock", "ollama", "claude-code", "codex"),
        help="通常は ollama。",
        tag="議事録抽出時",
        why="議事録（meeting）取り込み時にアクションタスクを抽出するAIの種類です。抽出は"
            "社内（on-prem）で完結し、生のトランスクリプトを外部に送りません。",
        steps=(
            "mock: 抽出しない（動作確認用）。",
            "ollama: ローカルの Ollama を使う（推奨・無料）。下の Ollama 設定が必要。",
            "claude-code / codex: それぞれの CLI を内部起動（サブスク前提・トークン課金なし）。",
        ),
        how_to_set="無料でローカル完結したいなら ollama を選択。",
    ),
    ConfigField(
        "OLLAMA_BASE_URL", "Ollama URL", "AI（議事録→タスク抽出）",
        help="通常 http://localhost:11434。",
        tag="ollama時",
        why="llm_provider=ollama のときの接続先です。",
        steps=(
            "https://ollama.com からインストール。",
            "ollama serve で起動（既定で http://localhost:11434 で待ち受け）。",
        ),
        how_to_set="同じPCなら既定の http://localhost:11434 のままでOK。",
    ),
    ConfigField(
        "OLLAMA_MODEL", "Ollama モデル", "AI（議事録→タスク抽出）",
        help="例 llama3。", tag="ollama時",
        why="抽出に使う Ollama のモデル名です。",
        steps=("使うモデルを取得: 例 ollama pull llama3。",),
        how_to_set="取得済みモデル名を入力（例 llama3）。",
    ),
    # ------------------------------------------------------------ Embedding
    ConfigField(
        "EMBEDDING_PROVIDER", "埋め込みモデル", "埋め込み（検索）", kind="select",
        options=("mock", "bge-m3"), restart_required=True,
        help="本番運用は bge-m3 推奨。",
        tag="意味検索を使うなら",
        why="ハイブリッド検索のベクトル（意味）側で使うモデルです。mock はハッシュで意味検索が"
            "効かない動作確認用。bge-m3 はローカルで本物の意味検索ができます。",
        steps=(
            "bge-m3 を使うには pip install 'yohakuforce-context-hub[embedding]'。",
            "初回は約2.3GBのモデルがダウンロードされます。",
            "選択後はサーバを再起動。",
        ),
        how_to_set="意味検索をちゃんと使うなら bge-m3 を選択。",
    ),
    ConfigField(
        "EMBEDDING_DEVICE", "計算デバイス", "埋め込み（検索）", kind="select",
        options=("cpu", "cuda"), restart_required=True,
        help="通常 cpu。", tag="bge-m3時",
        why="bge-m3 の計算に使うデバイス。対応GPUがあれば cuda が速いです。",
        how_to_set="GPUが無ければ cpu。",
    ),
    # ---------------------------------------------------------------- Slack
    ConfigField(
        "SLACK_BOT_TOKEN", "Slack Botトークン", "Slack", secret=True,
        tag="Slack取り込み時",
        why="Slack のメッセージ/スレッドをアダプタ同期で取り込むための Bot トークンです。"
            "スクレイピング取り込み（/ingest/slack）だけを使う場合はトークン不要です。",
        steps=(
            "https://api.slack.com/apps を開き「Create New App」→"
            "「From scratch」→ ワークスペース選択。",
            "「OAuth & Permissions」→ Scopes →「Bot Token Scopes」に channels:history と "
            "channels:read（必要に応じ groups:history 等）を追加。",
            "同ページ上部「Install to Workspace」→ 許可。",
            "「Bot User OAuth Token」（xoxb- で始まる）をコピー。",
            "取り込みたいチャンネルで /invite @アプリ名 を実行して Bot を招待。",
        ),
        how_to_set="「変更」を押して xoxb-… を貼り付け → 保存。",
    ),
    # -------------------------------------------------------------- Backlog
    ConfigField(
        "BACKLOG_API_KEY", "Backlog APIキー", "Backlog", secret=True,
        tag="Backlog取り込み時",
        why="Backlog の課題・コメント・Wiki を取り込むための API キーです。",
        steps=(
            "Backlog にログイン → 右上アイコン →「個人設定」→「API」。",
            "「登録」で新しいAPIキーを発行し、表示された文字列をコピー。",
        ),
        how_to_set="「変更」を押して貼り付け → 保存。下のスペースキーも設定。",
    ),
    ConfigField(
        "BACKLOG_SPACE_KEY", "Backlog スペース", "Backlog",
        tag="Backlog取り込み時",
        why="どの Backlog スペースに接続するかの指定です。",
        steps=(
            "Backlog の URL を確認: https://〈スペース〉.backlog.com（または .jp）。",
            "その〈スペース〉.backlog.com（ホスト名全体）がスペースキーです。",
        ),
        how_to_set="例 myteam.backlog.jp を入力。",
    ),
    # -------------------------------------------------------------- Redmine
    ConfigField(
        "REDMINE_API_KEY", "Redmine APIキー", "Redmine", secret=True,
        tag="Redmine取り込み時",
        why="Redmine の課題・Wiki を取り込むための API アクセスキーです。",
        steps=(
            "Redmine にログイン →「個人設定」。",
            "右側「APIアクセスキー」→「表示」でコピー（無ければ管理者が REST API を有効化）。",
        ),
        how_to_set="「変更」を押して貼り付け → 保存。下のベースURLも設定。",
    ),
    ConfigField(
        "REDMINE_BASE_URL", "Redmine URL", "Redmine",
        tag="Redmine取り込み時",
        why="接続先 Redmine の URL です。",
        steps=("Redmine トップページの URL（例 https://redmine.example.com）。末尾の / は不要。",),
        how_to_set="例 https://redmine.example.com を入力。",
    ),
    # ---------------------------------------------------------------- Gmail
    ConfigField(
        "GMAIL_CREDENTIALS_FILE", "Gmail 認証情報ファイル", "Gmail",
        tag="Gmail取り込み時",
        why="Gmail からメールを取り込むための OAuth2 認証情報（credentials.json）の置き場所です。"
            "既定では context-hub ラベルを付けたメールだけ取り込み、私信は索引に入れません。",
        steps=(
            "依存をインストール: pip install 'yohakuforce-context-hub[gmail]'。",
            "https://console.cloud.google.com でプロジェクトを作成/選択。",
            "「APIとサービス」→「ライブラリ」→ Gmail API を有効化。",
            "「APIとサービス」→「認証情報」→「認証情報を作成」→"
            "「OAuthクライアントID」→ 種類「デスクトップ」。",
            "credentials.json をダウンロードし安全な場所に保存"
            "（例 ~/.context-hub/gmail/credentials.json）。",
            "取り込みたいメールに Gmail で context-hub ラベルを付ける。",
        ),
        how_to_set="保存した credentials.json の絶対パスを入力。"
                   "初回 live 同期時にブラウザ同意すると下のトークンファイルが自動作成されます。",
    ),
    ConfigField(
        "GMAIL_TOKEN_FILE", "Gmail トークンファイル", "Gmail",
        tag="Gmail取り込み時",
        why="初回認証後の更新トークン（refresh token）のキャッシュ先です。これがあれば次回以降は"
            "同意不要。パスワード同等に扱い、コミットしないでください。",
        steps=("まだ無くてOK。保存先のパスだけ決めて入力（例 ~/.context-hub/gmail/token.json）。",),
        how_to_set="保存先パスを入力。",
    ),
    ConfigField(
        "GMAIL_QUERY", "Gmail 検索クエリ", "Gmail",
        help="既定 label:context-hub のままが安全。",
        tag="Gmail取り込み時",
        why="取り込み対象を絞る Gmail 検索クエリです。既定はラベル明示の opt-in で、私信を"
            "索引に入れないようにしています。",
        steps=(
            "Gmail の検索構文がそのまま使えます"
            "（例 label:context-hub、from:client@example.com newer_than:30d）。",
        ),
        how_to_set="通常は既定 label:context-hub のままでOK。",
    ),
    # ------------------------------------------------------------ Ingestion
    ConfigField(
        "INGEST_MODE", "取り込みモード", "取り込み", kind="select",
        options=("mock", "live"),
        help="実運用は live。",
        tag="基本",
        why="live=実際の外部API/認証情報を使って取り込む。mock=同梱サンプルデータ（動作確認用）。",
        how_to_set="本番運用は live。まず動作確認だけなら mock。",
    ),
    ConfigField(
        "CH_SOURCE_SYNC_ENABLED", "serve中の自動同期", "取り込み", kind="bool",
        restart_required=True,
        help="自動運用したいなら true。",
        tag="自動化",
        why="context-hub serve の起動中に、有効な全ソースを各 syncInterval ごとに自動同期"
            "するかどうかです（Inbox 監視も同様に動きます）。",
        how_to_set="サーバを立てっぱなしで自動同期したいなら true。",
    ),
    # ------------------------------------------------------------ Inbox watcher
    ConfigField(
        "CH_INBOX_DIR", "Inbox フォルダ", "Inbox 監視", restart_required=True,
        tag="メモ取り込み時",
        why="このフォルダに .md/.txt を置くだけで自動取り込みします（会議メモ等）。コマンド不要。"
            "空にすると無効です。",
        steps=(
            "任意の場所を作成: 例 mkdir -p ~/.context-hub/inbox/{meeting,file,email}",
            "meeting / file / email のサブフォルダに応じて種別が決まります。",
        ),
        how_to_set="例 ~/.context-hub/inbox を入力。",
    ),
    ConfigField(
        "CH_INBOX_POLL_SECONDS", "Inbox 確認間隔（秒）", "Inbox 監視", kind="int",
        restart_required=True, help="既定 60。",
        why="Inbox フォルダを確認する間隔（秒）です。",
        how_to_set="通常 60 のままでOK。",
    ),
    ConfigField(
        "CH_PROJECT_ID", "Inbox の対象プロジェクト", "Inbox 監視",
        why="プロジェクトが複数あるとき、Inbox 取り込み先を固定する ID です。",
        steps=("Sources タブで作成したプロジェクトの ID を確認。",),
        how_to_set="プロジェクトが1つだけなら空でOK。複数あるなら対象の ID を入力。",
    ),
)

_FIELD_BY_ENV: dict[str, ConfigField] = {f.env: f for f in FIELDS}


def mask_secret(value: str) -> str:
    """Return a masked hint for a secret, revealing at most the last 4 chars."""
    if not value:
        return ""
    if len(value) <= 4:
        return _MASK
    return f"{_MASK}{value[-4:]}"


@dataclass(frozen=True)
class FieldView:
    """A field's current state for the GUI (value masked when secret)."""

    env: str
    label: str
    group: str
    secret: bool
    kind: str
    options: tuple[str, ...]
    help: str
    restart_required: bool
    tag: str
    why: str
    steps: tuple[str, ...]
    how_to_set: str
    configured: bool
    value: str  # masked hint for secrets; raw value otherwise; "" when unset


def read_config(env_path: Path = DEFAULT_ENV_PATH) -> list[FieldView]:
    """Return every editable field with its current ``.env`` value (secrets masked)."""
    raw: dict[str, str | None] = dotenv_values(str(env_path)) if env_path.exists() else {}
    views: list[FieldView] = []
    for f in FIELDS:
        current = raw.get(f.env)
        configured = current is not None and current != ""
        if not configured:
            display = ""
        elif f.secret:
            display = mask_secret(current or "")
        else:
            display = current or ""
        views.append(
            FieldView(
                env=f.env, label=f.label, group=f.group, secret=f.secret, kind=f.kind,
                options=f.options, help=f.help, restart_required=f.restart_required,
                tag=f.tag, why=f.why, steps=f.steps, how_to_set=f.how_to_set,
                configured=configured, value=display,
            )
        )
    return views


@dataclass(frozen=True)
class WriteResult:
    """Outcome of a config write."""

    changed: list[str] = field(default_factory=list)
    cleared: list[str] = field(default_factory=list)
    restart_required: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)


def write_config(
    updates: dict[str, str | None], env_path: Path = DEFAULT_ENV_PATH
) -> WriteResult:
    """Apply ``updates`` to the ``.env`` file.

    Per entry: None → skip; "" → unset the key; string → set/replace it. Unknown
    keys are rejected and reported, never written.
    """
    changed: list[str] = []
    cleared: list[str] = []
    restart: list[str] = []
    rejected: list[str] = []

    if not env_path.exists():
        env_path.touch(mode=0o600)

    for env_key, value in updates.items():
        spec = _FIELD_BY_ENV.get(env_key)
        if spec is None:
            rejected.append(env_key)
            continue
        if value is None:
            continue
        if value == "":
            unset_key(str(env_path), env_key)
            cleared.append(env_key)
        else:
            set_key(str(env_path), env_key, value, quote_mode="never")
            changed.append(env_key)
        if spec.restart_required and env_key not in restart:
            restart.append(env_key)

    return WriteResult(
        changed=changed, cleared=cleared, restart_required=restart, rejected=rejected
    )


def reload_runtime_settings() -> None:
    """Re-read ``.env`` into the live settings singleton and clear the profile cache.

    Lets newly-saved values that are *not* restart-required (tokens, URLs, queries,
    credentials, ingest mode) take effect for subsequent REST ingests and scheduled
    syncs without restarting the process. Restart-required fields (database URL,
    profile, embedding, scheduler/inbox wiring) still need a restart.
    """
    from context_hub.config import settings as _legacy
    from context_hub.config.profiles import get_profile_settings

    fresh = type(_legacy)()
    for name in type(fresh).model_fields:
        setattr(_legacy, name, getattr(fresh, name))
    get_profile_settings.cache_clear()
