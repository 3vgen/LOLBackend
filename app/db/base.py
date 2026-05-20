from sqlalchemy.orm import declarative_base

Base = declarative_base()
# from app.users.models.model_user import User          # noqa: F401, E402
# from app.users.models.model_refresh_token import RefreshToken  # noqa: F401, E402
from app.models.test_model import TestTable  # noqa: F401, E402
from app.models.player import Player  # noqa: F401, E402
from app.models.ranked_entry import RankedEntry  # noqa: F401, E402
from app.models.match import Match  # noqa: F401, E402
from app.models.match_participant import MatchParticipant  # noqa: F401, E402

