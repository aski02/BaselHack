"""Response schemas for API endpoints"""

from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class StoreSubmissionsResponse(BaseModel):
    """Response schema for storing submissions"""
    ids: List[str]
    message: str
    count: int


class ClusterResponse(BaseModel):
    """Response schema for clustering"""
    clusters: List[List[str]]
    num_clusters: int
    silhouette_score: float


class AgentInfo(BaseModel):
    """Agent metadata"""
    agent_id: str
    agent_name: str
    cluster_id: int
    persona_summary: str


class MessageResponse(BaseModel):
    """Individual message in debate"""
    message_id: str
    content: str
    agent_id: str
    agent_name: str
    round_number: int
    message_type: str
    timestamp: str


class InterventionResponse(BaseModel):
    """Orchestrator intervention"""
    intervention_id: str
    intervention_type: str
    reason: str
    message: str
    timestamp: str


class CreateDebateResponse(BaseModel):
    """Response for creating a debate"""
    debate_id: str
    status: str
    agents: List[AgentInfo]
    created_at: str


class DebateListResponse(BaseModel):
    """List of debates"""
    debates: List[dict]  # Simplified for listing


class DebateResponse(BaseModel):
    """Full debate details"""
    debate_id: str
    project_id: str
    status: str
    consensus_score: Optional[float]
    error_message: Optional[str] = None
    agents: List[AgentInfo]
    messages: List[MessageResponse]
    interventions: List[InterventionResponse]
    created_at: str
    updated_at: str


class ConsensusResponse(BaseModel):
    """Consensus analysis response"""
    consensus_score: float
    semantic_alignment: float
    agreement_ratio: float
    convergence_score: float
    resolution_rate: float
    sentiment: str
    key_alignments: List[str]
    key_insights: List[str]
    pro_arguments: List[str]
    con_arguments: List[str]
    pairwise_alignment: Optional[dict] = None

