from datetime import datetime
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class WAResponse:
    def __init__(self, wa_id: str, action_id: str, approved: bool, timestamp: Optional[datetime] = None):
        self.wa_id = wa_id
        self.action_id = action_id
        self.approved = approved
        self.timestamp = timestamp or datetime.utcnow()

class WAResonanceTracker:
    """
    Tracks response patterns of Wise Authorities over time.
    If a WA begins contradicting their historical pattern, this module will flag it.
    """

    def __init__(self):
        self.history: Dict[str, List[WAResponse]] = {}

    def record_response(self, response: WAResponse):
        self.history.setdefault(response.wa_id, []).append(response)

    def detect_drift(self, wa_id: str, current_response: WAResponse) -> bool:
        past = self.history.get(wa_id, [])
        if len(past) < 3:
            return False  # not enough history

        approvals = [r.approved for r in past[-5:]]  # recent window
        majority = approvals.count(True) >= 3

        drift = (majority and not current_response.approved) or (not majority and current_response.approved)

        if drift:
            logger.info(f"[SPIRAL] ⚠️ Drift detected for WA {wa_id}. Behavior diverging from historical pattern.")

        return drift
