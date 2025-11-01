"""Debate storage service using MongoDB for persistence"""

from pymongo import MongoClient, ASCENDING, DESCENDING
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime
from app.core import config

_client = None
_db = None


def get_mongo_client() -> MongoClient:
    """
    Get or create MongoDB client singleton
    
    Returns:
        MongoClient instance
    """
    global _client
    if _client is None:
        _client = MongoClient(config.MONGODB_URL)
    return _client


def get_database():
    """
    Get or create the database instance
    
    Returns:
        Database instance with indexes created
    """
    global _db
    if _db is None:
        client = get_mongo_client()
        _db = client[config.MONGODB_DB_NAME]
        _create_indexes()
    return _db


def _create_indexes():
    """Create indexes for better query performance"""
    db = get_database()
    
    # Debates collection indexes
    db.debates.create_index([("project_id", ASCENDING)])
    db.debates.create_index([("status", ASCENDING)])
    db.debates.create_index([("created_at", DESCENDING)])
    
    # Messages collection indexes
    db.messages.create_index([("debate_id", ASCENDING), ("round_number", ASCENDING), ("timestamp", ASCENDING)])
    db.messages.create_index([("debate_id", ASCENDING), ("agent_id", ASCENDING)])
    db.messages.create_index([("debate_id", ASCENDING), ("timestamp", ASCENDING)])
    
    # Agents collection indexes
    db.agents.create_index([("debate_id", ASCENDING)])
    db.agents.create_index([("debate_id", ASCENDING), ("agent_id", ASCENDING)], unique=True)
    
    # Interventions collection indexes
    db.interventions.create_index([("debate_id", ASCENDING), ("timestamp", ASCENDING)])
    
    # Consensus and summaries are keyed by debate_id (unique)


def create_debate(project_id: str, status: str = "pending") -> str:
    """
    Create a new debate session
    
    Args:
        project_id: Project identifier
        status: Initial status (pending, running, completed, cancelled)
    
    Returns:
        Debate ID
    """
    debate_id = str(uuid.uuid4())
    db = get_database()
    
    debate_doc = {
        "_id": debate_id,
        "project_id": project_id,
        "status": status,
        "consensus_score": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    
    db.debates.insert_one(debate_doc)
    return debate_id


def get_debate(debate_id: str) -> Optional[Dict[str, Any]]:
    """
    Get debate by ID
    
    Args:
        debate_id: Debate identifier
        
    Returns:
        Dictionary with debate data or None if not found
    """
    db = get_database()
    debate = db.debates.find_one({"_id": debate_id})
    
    if not debate:
        return None
    
    # Convert ObjectId and datetime to strings for JSON serialization
    return {
        "debate_id": debate["_id"],
        "project_id": debate["project_id"],
        "status": debate["status"],
        "consensus_score": debate.get("consensus_score"),
        "created_at": debate["created_at"].isoformat() if isinstance(debate["created_at"], datetime) else debate["created_at"],
        "updated_at": debate["updated_at"].isoformat() if isinstance(debate["updated_at"], datetime) else debate["updated_at"],
    }


def update_debate_status(
    debate_id: str, 
    status: str, 
    consensus_score: Optional[float] = None,
    error_message: Optional[str] = None
) -> None:
    """
    Update debate status and optionally consensus score and error message
    
    Args:
        debate_id: Debate identifier
        status: New status (pending, running, completed, cancelled)
        consensus_score: Optional consensus score to update
        error_message: Optional error message to store
        
    Raises:
        ValueError: If debate not found
    """
    db = get_database()
    
    update_doc = {
        "$set": {
            "status": status,
            "updated_at": datetime.utcnow(),
        }
    }
    
    if consensus_score is not None:
        update_doc["$set"]["consensus_score"] = consensus_score
    
    if error_message is not None:
        update_doc["$set"]["error_message"] = error_message
    
    result = db.debates.update_one({"_id": debate_id}, update_doc)
    
    if result.matched_count == 0:
        raise ValueError(f"Debate {debate_id} not found")


def list_debates(project_id: str) -> List[Dict[str, Any]]:
    """
    List all debates for a project
    
    Args:
        project_id: Project identifier
        
    Returns:
        List of debate dictionaries, sorted by creation date (newest first)
    """
    db = get_database()
    debates = db.debates.find({"project_id": project_id}).sort("created_at", DESCENDING)
    
    result = []
    for debate in debates:
        result.append({
            "debate_id": debate["_id"],
            "status": debate["status"],
            "consensus_score": debate.get("consensus_score"),
            "created_at": debate["created_at"].isoformat() if isinstance(debate["created_at"], datetime) else debate["created_at"],
            "updated_at": debate["updated_at"].isoformat() if isinstance(debate["updated_at"], datetime) else debate["updated_at"],
        })
    
    return result


def add_debate_agent(
    debate_id: str, 
    agent_id: str, 
    agent_name: str, 
    cluster_id: int, 
    persona_summary: str
) -> None:
    """
    Add an agent participant to a debate
    
    Args:
        debate_id: Debate identifier
        agent_id: Unique agent identifier
        agent_name: Display name for the agent
        cluster_id: Cluster index this agent represents
        persona_summary: Summary of agent's persona/backstory
    """
    db = get_database()
    
    agent_doc = {
        "debate_id": debate_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "cluster_id": cluster_id,
        "persona_summary": persona_summary,
    }
    
    # Use upsert to avoid duplicates
    db.agents.update_one(
        {"debate_id": debate_id, "agent_id": agent_id},
        {"$set": agent_doc},
        upsert=True
    )


def get_debate_agents(debate_id: str) -> List[Dict[str, Any]]:
    """
    Get all agents participating in a debate
    
    Args:
        debate_id: Debate identifier
        
    Returns:
        List of agent dictionaries with agent_id, agent_name, cluster_id, persona_summary
    """
    db = get_database()
    agents = db.agents.find({"debate_id": debate_id})
    
    result = []
    for agent in agents:
        result.append({
            "agent_id": agent["agent_id"],
            "agent_name": agent["agent_name"],
            "cluster_id": agent["cluster_id"],
            "persona_summary": agent["persona_summary"],
        })
    
    return result


def add_debate_message(
    debate_id: str,
    agent_id: str,
    agent_name: str,
    content: str,
    round_number: int,
    message_type: str = "agent_message"
) -> str:
    """
    Add a message to the debate
    
    Args:
        debate_id: Debate identifier
        agent_id: Agent identifier
        agent_name: Agent name
        content: Message content
        round_number: Round number
        message_type: Type of message (agent_message, orchestrator_message, intervention)
    
    Returns:
        Message ID
    """
    message_id = str(uuid.uuid4())
    db = get_database()
    timestamp = datetime.utcnow()
    
    message_doc = {
        "_id": message_id,
        "debate_id": debate_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "content": content,
        "round_number": round_number,
        "message_type": message_type,
        "timestamp": timestamp,
    }
    
    db.messages.insert_one(message_doc)
    return message_id


def get_debate_messages(
    debate_id: str,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    agent_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get messages for a debate with optional pagination and filtering
    
    Returns:
        Dictionary with messages list and total count
    """
    db = get_database()
    
    # Build query
    query = {"debate_id": debate_id}
    if agent_id:
        query["agent_id"] = agent_id
    
    # Get total count
    total = db.messages.count_documents(query)
    
    # Build cursor with sorting
    cursor = db.messages.find(query).sort([
        ("round_number", ASCENDING),
        ("timestamp", ASCENDING)
    ])
    
    # Apply pagination
    if offset:
        cursor = cursor.skip(offset)
    if limit:
        cursor = cursor.limit(limit)
    
    messages = []
    for msg in cursor:
        messages.append({
            "message_id": msg["_id"],
            "content": msg["content"],
            "agent_id": msg["agent_id"],
            "agent_name": msg["agent_name"],
            "round_number": msg["round_number"],
            "message_type": msg["message_type"],
            "timestamp": msg["timestamp"].isoformat() if isinstance(msg["timestamp"], datetime) else msg["timestamp"],
        })
    
    return {
        "messages": messages,
        "total": total,
        "limit": limit,
        "offset": offset or 0,
    }


def add_intervention(
    debate_id: str,
    intervention_type: str,
    reason: str,
    message: Optional[str] = None
) -> str:
    """
    Add an orchestrator intervention
    
    Args:
        debate_id: Debate identifier
        intervention_type: Type of intervention (repetition, off_topic, stalemate, max_rounds, ethical)
        reason: Reason for intervention
        message: Optional intervention message
    
    Returns:
        Intervention ID
    """
    intervention_id = str(uuid.uuid4())
    db = get_database()
    timestamp = datetime.utcnow()
    
    intervention_doc = {
        "_id": intervention_id,
        "debate_id": debate_id,
        "intervention_type": intervention_type,
        "reason": reason,
        "message": message or reason,
        "timestamp": timestamp,
    }
    
    db.interventions.insert_one(intervention_doc)
    return intervention_id


def get_debate_interventions(debate_id: str) -> List[Dict[str, Any]]:
    """
    Get all interventions for a debate
    
    Args:
        debate_id: Debate identifier
        
    Returns:
        List of intervention dictionaries sorted by timestamp
    """
    db = get_database()
    interventions = db.interventions.find({"debate_id": debate_id}).sort("timestamp", ASCENDING)
    
    result = []
    for intervention in interventions:
        result.append({
            "intervention_id": intervention["_id"],
            "intervention_type": intervention["intervention_type"],
            "reason": intervention["reason"],
            "message": intervention["message"],
            "timestamp": intervention["timestamp"].isoformat() if isinstance(intervention["timestamp"], datetime) else intervention["timestamp"],
        })
    
    return result


def store_consensus_analysis(
    debate_id: str,
    consensus_score: float,
    semantic_alignment: float,
    agreement_ratio: float,
    convergence_score: float,
    resolution_rate: float,
    sentiment: str
) -> None:
    """
    Store consensus analysis results for a debate
    
    Args:
        debate_id: Debate identifier
        consensus_score: Overall consensus score (0-100)
        semantic_alignment: Semantic alignment score (0-1)
        agreement_ratio: Agreement ratio (0-1)
        convergence_score: Convergence score (0-1)
        resolution_rate: Resolution rate (0-1)
        sentiment: Overall sentiment (positive, neutral, negative)
    """
    db = get_database()
    timestamp = datetime.utcnow()
    
    consensus_doc = {
        "_id": debate_id,
        "debate_id": debate_id,
        "consensus_score": consensus_score,
        "semantic_alignment": semantic_alignment,
        "agreement_ratio": agreement_ratio,
        "convergence_score": convergence_score,
        "resolution_rate": resolution_rate,
        "sentiment": sentiment,
        "calculated_at": timestamp,
    }
    
    # Use upsert to replace existing consensus
    db.consensus.update_one(
        {"_id": debate_id},
        {"$set": consensus_doc},
        upsert=True
    )


def get_consensus_analysis(debate_id: str) -> Optional[Dict[str, Any]]:
    """
    Get consensus analysis for a debate
    
    Args:
        debate_id: Debate identifier
        
    Returns:
        Dictionary with consensus metrics or None if not found
    """
    db = get_database()
    consensus = db.consensus.find_one({"_id": debate_id})
    
    if not consensus:
        return None
    
    return {
        "debate_id": consensus["debate_id"],
        "consensus_score": consensus["consensus_score"],
        "semantic_alignment": consensus["semantic_alignment"],
        "agreement_ratio": consensus["agreement_ratio"],
        "convergence_score": consensus["convergence_score"],
        "resolution_rate": consensus["resolution_rate"],
        "sentiment": consensus["sentiment"],
        "calculated_at": consensus["calculated_at"].isoformat() if isinstance(consensus["calculated_at"], datetime) else consensus["calculated_at"],
    }


def store_debate_summary(
    debate_id: str,
    key_alignments: List[str],
    key_insights: List[str],
    pro_arguments: List[str],
    con_arguments: List[str]
) -> None:
    """
    Store debate summary
    
    Args:
        debate_id: Debate identifier
        key_alignments: List of key alignment points
        key_insights: List of key insights
        pro_arguments: List of pro arguments
        con_arguments: List of con arguments
    """
    db = get_database()
    timestamp = datetime.utcnow()
    
    summary_doc = {
        "_id": debate_id,
        "debate_id": debate_id,
        "key_alignments": key_alignments,
        "key_insights": key_insights,
        "pro_arguments": pro_arguments,
        "con_arguments": con_arguments,
        "generated_at": timestamp,
    }
    
    # Use upsert to replace existing summary
    db.summaries.update_one(
        {"_id": debate_id},
        {"$set": summary_doc},
        upsert=True
    )


def get_debate_summary(debate_id: str) -> Optional[Dict[str, Any]]:
    """
    Get debate summary
    
    Args:
        debate_id: Debate identifier
        
    Returns:
        Dictionary with summary data or None if not found
    """
    db = get_database()
    summary = db.summaries.find_one({"_id": debate_id})
    
    if not summary:
        return None
    
    return {
        "debate_id": summary["debate_id"],
        "key_alignments": summary["key_alignments"],
        "key_insights": summary["key_insights"],
        "pro_arguments": summary["pro_arguments"],
        "con_arguments": summary["con_arguments"],
        "generated_at": summary["generated_at"].isoformat() if isinstance(summary["generated_at"], datetime) else summary["generated_at"],
    }
