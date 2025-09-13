from pydantic_settings import BaseSettings


class LineSettings(BaseSettings):
    LINE_ACCESS_TOKEN: str
    LINE_CHANNEL_SECRET: str
    ALLOWED_GROUP_IDS: str = ""  # 逗號分隔的群組ID列表

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def allowed_groups(self) -> list[str]:
        """返回允許的群組ID列表"""
        if not self.ALLOWED_GROUP_IDS:
            return []
        return [gid.strip() for gid in self.ALLOWED_GROUP_IDS.split(",")]


class AgentSettings(BaseSettings):
    FIRECRAWL_API_KEY: str
    OPENAI_API_KEY: str
    GEMINI_API_KEY: str
    Mem0_API_Key: str
    Google_API_Key: str

    class Config:
        env_file = ".env"
        extra = "ignore"


agent_settings = AgentSettings()
line_settings = LineSettings()
