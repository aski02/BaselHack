"""Consensus and alignment analysis service"""

import numpy as np
from typing import List, Dict, Any
from sklearn.metrics.pairwise import cosine_similarity
from textblob import TextBlob
from app.services.clustering import get_model
from app.services.debate_storage import get_debate_messages, get_debate_agents
from app.core import config


def calculate_consensus_score(debate_id: str) -> Dict[str, Any]:
    """
    Calculate comprehensive consensus score and metrics for a debate
    
    Args:
        debate_id: Debate identifier
        
    Returns:
        Dictionary with:
        - consensus_score: Overall score (0-100)
        - semantic_alignment: Semantic alignment percentage (0-100)
        - agreement_ratio: Agreement ratio percentage (0-100)
        - convergence_score: Convergence score percentage (0-100)
        - resolution_rate: Resolution rate percentage (0-100)
        - sentiment: Overall sentiment (positive, neutral, negative)
    """
    messages_data = get_debate_messages(debate_id)
    messages = messages_data["messages"]
    
    if not messages:
        return {
            "consensus_score": 0.0,
            "semantic_alignment": 0.0,
            "agreement_ratio": 0.0,
            "convergence_score": 0.0,
            "resolution_rate": 0.0,
            "sentiment": "neutral",
        }
    
    # 1. Semantic Alignment Score
    semantic_alignment = calculate_semantic_alignment(messages)
    
    # 2. Explicit Agreement Ratio
    agreement_ratio = calculate_agreement_ratio(messages)
    
    # 3. Convergence Over Time
    convergence_score = calculate_convergence(messages)
    
    # 4. Argument Resolution Rate
    resolution_rate = calculate_resolution_rate(messages)
    
    # Calculate final consensus score
    consensus_score = (
        semantic_alignment * 100 * config.CONSENSUS_SEMANTIC_WEIGHT +
        agreement_ratio * 100 * config.CONSENSUS_AGREEMENT_WEIGHT +
        convergence_score * 100 * config.CONSENSUS_CONVERGENCE_WEIGHT +
        resolution_rate * 100 * config.CONSENSUS_RESOLUTION_WEIGHT
    )
    
    # Calculate sentiment
    sentiment = calculate_sentiment(messages)
    
    return {
        "consensus_score": round(consensus_score, 2),
        "semantic_alignment": round(semantic_alignment * 100, 2),
        "agreement_ratio": round(agreement_ratio * 100, 2),
        "convergence_score": round(convergence_score * 100, 2),
        "resolution_rate": round(resolution_rate * 100, 2),
        "sentiment": sentiment,
    }


def calculate_semantic_alignment(messages: List[Dict[str, Any]]) -> float:
    """
    Calculate semantic alignment by comparing final agent positions
    
    Returns:
        Semantic alignment score (0.0 to 1.0)
    """
    if len(messages) < 2:
        return 0.0
    
    # Group messages by agent and get their latest positions
    agents = {}
    for msg in messages:
        agent_id = msg["agent_id"]
        if agent_id not in agents or msg["round_number"] > agents[agent_id]["round"]:
            agents[agent_id] = {
                "content": msg["content"],
                "round": msg["round_number"],
            }
    
    if len(agents) < 2:
        return 0.0
    
    # Get final positions (last 2-3 messages per agent to capture position)
    agent_positions = []
    for agent_id, agent_data in agents.items():
        agent_positions.append(agent_data["content"])
    
    # Embed all positions
    model = get_model()
    embeddings = model.encode(agent_positions, convert_to_numpy=True, normalize_embeddings=True)
    
    # Calculate pairwise cosine similarities
    similarities = cosine_similarity(embeddings)
    
    # Get upper triangle (excluding diagonal) for pairwise comparisons
    n = len(similarities)
    if n < 2:
        return 0.0
    
    pairwise_sims = []
    for i in range(n):
        for j in range(i + 1, n):
            pairwise_sims.append(similarities[i][j])
    
    # Average similarity is our alignment score
    return float(np.mean(pairwise_sims)) if pairwise_sims else 0.0


def calculate_agreement_ratio(messages: List[Dict[str, Any]]) -> float:
    """
    Calculate ratio of explicit agreement vs disagreement statements
    
    Returns:
        Agreement ratio (0.0 to 1.0, where 1.0 means all agreements)
    """
    agreement_keywords = [
        "agree", "support", "same view", "concur", "endorse", "approve",
        "align", "similar", "shared", "common ground", "together", "united"
    ]
    
    disagreement_keywords = [
        "disagree", "oppose", "against", "different", "contrary", "reject",
        "conflict", "dispute", "challenge", "differ", "divergent"
    ]
    
    agreement_count = 0
    disagreement_count = 0
    
    for msg in messages:
        content_lower = msg["content"].lower()
        
        # Count agreement indicators
        for keyword in agreement_keywords:
            if keyword in content_lower:
                agreement_count += 1
                break
        
        # Count disagreement indicators
        for keyword in disagreement_keywords:
            if keyword in content_lower:
                disagreement_count += 1
                break
    
    total_statements = agreement_count + disagreement_count
    
    if total_statements == 0:
        return 0.5  # Neutral if no explicit agreements/disagreements
    
    return agreement_count / total_statements


def calculate_convergence(messages: List[Dict[str, Any]]) -> float:
    """
    Measure how agent positions converge over time
    
    Returns:
        Convergence score (0.0 to 1.0)
    """
    if len(messages) < 4:
        return 0.0
    
    # Split messages into early and late rounds
    max_round = max(msg["round_number"] for msg in messages)
    mid_point = max_round // 2
    
    early_messages = [msg for msg in messages if msg["round_number"] <= mid_point]
    late_messages = [msg for msg in messages if msg["round_number"] > mid_point]
    
    if not early_messages or not late_messages:
        return 0.0
    
    # Get agent positions in early vs late stages
    early_positions = {}
    late_positions = {}
    
    for msg in early_messages:
        agent_id = msg["agent_id"]
        if agent_id not in early_positions:
            early_positions[agent_id] = []
        early_positions[agent_id].append(msg["content"])
    
    for msg in late_messages:
        agent_id = msg["agent_id"]
        if agent_id not in late_positions:
            late_positions[agent_id] = []
        late_positions[agent_id].append(msg["content"])
    
    # Get representative positions (last message per agent in each stage)
    early_reps = []
    late_reps = []
    
    for agent_id in early_positions:
        if agent_id in late_positions:
            early_reps.append(" ".join(early_positions[agent_id][-1:]))  # Last message
            late_reps.append(" ".join(late_positions[agent_id][-1:]))
    
    if len(early_reps) < 2:
        return 0.0
    
    # Embed and compare
    model = get_model()
    early_embeddings = model.encode(early_reps, convert_to_numpy=True, normalize_embeddings=True)
    late_embeddings = model.encode(late_reps, convert_to_numpy=True, normalize_embeddings=True)
    
    # Calculate pairwise similarities within early and late stages
    early_sim = cosine_similarity(early_embeddings)
    late_sim = cosine_similarity(late_embeddings)
    
    # Extract upper triangles
    n = len(early_sim)
    early_pairwise = []
    late_pairwise = []
    
    for i in range(n):
        for j in range(i + 1, n):
            early_pairwise.append(early_sim[i][j])
            late_pairwise.append(late_sim[i][j])
    
    if not early_pairwise or not late_pairwise:
        return 0.0
    
    early_avg = np.mean(early_pairwise)
    late_avg = np.mean(late_pairwise)
    
    # Convergence = increase in similarity over time
    convergence = max(0.0, late_avg - early_avg)
    
    # Normalize to 0-1 range (assuming similarity ranges from -1 to 1, convergence can be up to 2)
    return min(1.0, convergence / 0.5) if convergence > 0 else 0.0


def calculate_resolution_rate(messages: List[Dict[str, Any]]) -> float:
    """
    Calculate rate at which counter-arguments are addressed/resolved
    
    Returns:
        Resolution rate (0.0 to 1.0)
    """
    if len(messages) < 2:
        return 0.0
    
    # Track arguments and their resolutions
    arguments_raised = set()
    arguments_addressed = set()
    
    resolution_indicators = [
        "address", "respond", "resolve", "acknowledge", "understand", "consider",
        "accept", "incorporate", "modify", "refine", "update", "revise"
    ]
    
    # Scan messages for arguments and resolutions
    for i, msg in enumerate(messages):
        content = msg["content"].lower()
        
        # Detect if this is addressing a previous argument
        for indicator in resolution_indicators:
            if indicator in content:
                # Look back for arguments this might be addressing
                if i > 0:
                    arguments_addressed.add(messages[i - 1]["agent_id"])
                break
        
        # Track arguments (messages that contain disagreement or challenges)
        if any(word in content for word in ["but", "however", "although", "challenge", "question"]):
            arguments_raised.add(msg["agent_id"])
    
    total_arguments = len(arguments_raised)
    
    if total_arguments == 0:
        return 1.0  # No conflicts = full resolution
    
    resolved = len(arguments_addressed)
    return resolved / total_arguments if total_arguments > 0 else 1.0


def calculate_sentiment(messages: List[Dict[str, Any]]) -> str:
    """
    Calculate overall sentiment of the debate
    
    Returns:
        "positive", "neutral", or "negative"
    """
    if not messages:
        return "neutral"
    
    sentiments = []
    for msg in messages:
        blob = TextBlob(msg["content"])
        polarity = blob.sentiment.polarity
        sentiments.append(polarity)
    
    avg_sentiment = np.mean(sentiments)
    
    if avg_sentiment > 0.1:
        return "positive"
    elif avg_sentiment < -0.1:
        return "negative"
    else:
        return "neutral"


def calculate_pairwise_alignment_matrix(debate_id: str) -> Dict[str, Any]:
    """
    Calculate NxN pairwise alignment matrix between agents
    
    Returns:
        Dictionary with agent_ids and alignment matrix
    """
    agents = get_debate_agents(debate_id)
    messages_data = get_debate_messages(debate_id)
    messages = messages_data["messages"]
    
    if len(agents) < 2:
        return {
            "agent_ids": [a["agent_id"] for a in agents],
            "matrix": [],
        }
    
    # Get final positions per agent
    agent_positions = {}
    for msg in messages:
        agent_id = msg["agent_id"]
        if agent_id not in agent_positions or msg["round_number"] > agent_positions[agent_id]["round"]:
            agent_positions[agent_id] = {
                "content": msg["content"],
                "round": msg["round_number"],
            }
    
    # Build position texts in order
    agent_ids = [a["agent_id"] for a in agents]
    position_texts = []
    
    for agent_id in agent_ids:
        if agent_id in agent_positions:
            position_texts.append(agent_positions[agent_id]["content"])
        else:
            position_texts.append("")  # No position found
    
    # Embed and calculate similarities
    model = get_model()
    embeddings = model.encode(position_texts, convert_to_numpy=True, normalize_embeddings=True)
    similarity_matrix = cosine_similarity(embeddings)
    
    return {
        "agent_ids": agent_ids,
        "agent_names": [a["agent_name"] for a in agents],
        "matrix": similarity_matrix.tolist(),
    }


