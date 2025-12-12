"""
Message Ordering Integration Test.

Tests that messages sent concurrently to the same conversation
are processed and stored in the correct chronological order.

This validates:
1. Kafka partition key routing (conversation_id)
2. Sequential processing within partitions
3. Database ordering by created_at timestamp

Usage:
    pytest tests/integration/test_message_ordering.py -v
    
    Or run standalone:
    python tests/integration/test_message_ordering.py
"""
import asyncio
import time
import uuid
from datetime import datetime
from typing import List
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed


# Configuration
API_BASE_URL = "http://localhost:8000"
TEST_USERNAME = "user1"
TEST_PASSWORD = "password123"
MESSAGE_COUNT = 100  # Send 100 messages concurrently


def authenticate() -> str:
    """Authenticate and get access token."""
    response = requests.post(
        f"{API_BASE_URL}/auth/legacy/token",
        json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
    )
    response.raise_for_status()
    return response.json()["token"]


def create_test_conversation(token: str) -> int:
    """Create a test conversation."""
    response = requests.post(
        f"{API_BASE_URL}/v1/conversations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "type": "private",
            "member_ids": [1, 2]  # User 1 and User 2
        }
    )
    response.raise_for_status()
    return response.json()["id"]


def send_message(token: str, conversation_id: int, message_index: int) -> dict:
    """
    Send a message to the conversation.
    
    Args:
        token: Authentication token
        conversation_id: ID of the conversation
        message_index: Index of this message (0-99)
        
    Returns:
        dict with message_id, index, and timestamp
    """
    message_id = str(uuid.uuid4())
    send_time = datetime.utcnow()
    
    response = requests.post(
        f"{API_BASE_URL}/v1/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "message_id": message_id,
            "conversation_id": conversation_id,
            "payload": {
                "type": "text",
                "content": f"Test message {message_index:03d}"
            },
            "channels": ["whatsapp"]
        }
    )
    
    # Accept 202 Accepted or 200 OK
    if response.status_code not in [200, 202]:
        response.raise_for_status()
    
    return {
        "message_id": message_id,
        "index": message_index,
        "sent_at": send_time.isoformat(),
        "status_code": response.status_code
    }


def get_conversation_messages(token: str, conversation_id: int, limit: int = 200) -> List[dict]:
    """
    Get all messages from the conversation.
    
    Args:
        token: Authentication token
        conversation_id: ID of the conversation
        limit: Maximum messages to retrieve
        
    Returns:
        List of message dicts ordered by created_at
    """
    response = requests.get(
        f"{API_BASE_URL}/v1/conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
        params={"limit": limit}
    )
    response.raise_for_status()
    return response.json()["messages"]


def verify_message_ordering(messages: List[dict], expected_count: int) -> bool:
    """
    Verify that messages are in correct chronological order.
    
    Args:
        messages: List of messages from database
        expected_count: Expected number of messages
        
    Returns:
        True if ordering is correct, False otherwise
    """
    if len(messages) != expected_count:
        print(f"❌ Expected {expected_count} messages, got {len(messages)}")
        return False
    
    # Extract message indices from content
    indices = []
    for msg in messages:
        content = msg["payload"]["content"]
        # Extract number from "Test message 000"
        try:
            index = int(content.split()[-1])
            indices.append(index)
        except (ValueError, IndexError):
            print(f"❌ Failed to parse message index from: {content}")
            return False
    
    # Verify indices are in sequential order
    expected_sequence = list(range(expected_count))
    if indices == expected_sequence:
        print(f"✅ All {expected_count} messages in correct order!")
        return True
    else:
        # Find first out-of-order message
        for i, (expected, actual) in enumerate(zip(expected_sequence, indices)):
            if expected != actual:
                print(f"❌ Message ordering error at position {i}: expected {expected}, got {actual}")
                print(f"   Sequence around error: {indices[max(0,i-3):i+4]}")
                break
        return False


def run_integration_test():
    """Run the complete integration test."""
    print("=" * 70)
    print("MESSAGE ORDERING INTEGRATION TEST")
    print("=" * 70)
    print(f"Configuration:")
    print(f"  API URL: {API_BASE_URL}")
    print(f"  Messages to send: {MESSAGE_COUNT}")
    print(f"  Concurrency: ThreadPoolExecutor with {MESSAGE_COUNT} threads")
    print()
    
    # Step 1: Authenticate
    print("Step 1: Authenticating...")
    token = authenticate()
    print(f"✅ Authenticated successfully")
    print()
    
    # Step 2: Create test conversation
    print("Step 2: Creating test conversation...")
    conversation_id = create_test_conversation(token)
    print(f"✅ Created conversation ID: {conversation_id}")
    print()
    
    # Step 3: Send messages concurrently
    print(f"Step 3: Sending {MESSAGE_COUNT} messages concurrently...")
    start_time = time.time()
    sent_messages = []
    
    with ThreadPoolExecutor(max_workers=MESSAGE_COUNT) as executor:
        # Submit all message send operations
        futures = {
            executor.submit(send_message, token, conversation_id, i): i 
            for i in range(MESSAGE_COUNT)
        }
        
        # Collect results as they complete
        for future in as_completed(futures):
            try:
                result = future.result()
                sent_messages.append(result)
                
                # Progress indicator
                if len(sent_messages) % 10 == 0:
                    print(f"  Sent {len(sent_messages)}/{MESSAGE_COUNT} messages...")
            except Exception as e:
                index = futures[future]
                print(f"  ❌ Failed to send message {index}: {e}")
    
    send_duration = time.time() - start_time
    print(f"✅ Sent {len(sent_messages)} messages in {send_duration:.2f}s")
    print(f"   Throughput: {len(sent_messages)/send_duration:.1f} msg/s")
    print()
    
    # Step 4: Wait for message processing
    print("Step 4: Waiting for message processing...")
    print("  (Outbox poller publishes to Kafka, workers process messages)")
    time.sleep(10)  # Wait for outbox poller and workers
    print("✅ Processing window completed")
    print()
    
    # Step 5: Retrieve messages from database
    print("Step 5: Retrieving messages from database...")
    messages = get_conversation_messages(token, conversation_id, limit=MESSAGE_COUNT + 10)
    print(f"✅ Retrieved {len(messages)} messages")
    print()
    
    # Step 6: Verify ordering
    print("Step 6: Verifying message ordering...")
    ordering_correct = verify_message_ordering(messages, MESSAGE_COUNT)
    print()
    
    # Summary
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Messages sent:      {len(sent_messages)}/{MESSAGE_COUNT}")
    print(f"Messages retrieved: {len(messages)}")
    print(f"Send throughput:    {len(sent_messages)/send_duration:.1f} msg/s")
    print(f"Ordering correct:   {'✅ PASS' if ordering_correct else '❌ FAIL'}")
    print("=" * 70)
    
    return ordering_correct


if __name__ == "__main__":
    try:
        success = run_integration_test()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
