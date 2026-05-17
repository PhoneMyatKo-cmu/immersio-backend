from sqlalchemy import String, Integer, Float, ForeignKey,Enum,Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
import enum
from db.base import Base



class ConfidenceLevel(str, enum.Enum):
    high="high"
    medium="medium"
    low="low"
    
class AI_Explanation_Cache(Base):
    __tablename__="ai_explanation_cache"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    vocab_id:Mapped[int]=mapped_column(
        ForeignKey("vocabulary.id",ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    sentence_id:Mapped[int]=mapped_column(
        ForeignKey("sentences.id",ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    explanation:Mapped[str]=mapped_column(
        String(3000),
        nullable=False
    )
    
    examples:Mapped[list[dict]]=mapped_column(
        JSONB,
        nullable=False
        
    )
    
    confidence_level: Mapped[ConfidenceLevel] = mapped_column(
        Enum(ConfidenceLevel, name="confidence_level_enum"),
        nullable=False,
    )
    
    dictionary_mismatch_detected:Mapped[bool]=mapped_column(
        Boolean,
        nullable=False
    )
    
    