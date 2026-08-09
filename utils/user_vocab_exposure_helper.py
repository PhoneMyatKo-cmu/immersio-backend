
from sqlalchemy.orm import Session


def isIntervalOverlapping(first_start_time: float, first_end_time: float, second_start_time: float, second_end_time: float, tolerance: float = 0.3) -> bool:
    """
    Checks if first interval falls within the second interval with a tolerance.
    Parameters:
    - first_start_time: Start time of the first interval in seconds.
    - first_end_time: End time of the first interval in seconds.
    - second_start_time: Start time of the second interval in seconds.
    - second_end_time: End time of the second interval in seconds.
    - tolerance: Time tolerance in seconds to account for slight overlaps or discrepancies.
    Returns:
    - True if the first interval falls within the second interval, False otherwise.
    """

    return (first_start_time >= second_start_time - tolerance and first_end_time <= second_end_time + tolerance)

# def filter_intervals_within_video(intervals: list, video_id: int, user_id: int, db: Session) -> list:
#     """
#     Filters the provided intervals to only include those that cover new parts of the video that the user has not already been exposed to.
#     Parameters:
#     - intervals: List of LearningVideoInterval objects.
#     - video_id: ID of the video to check against.
#     - user_id: ID of the user (for logging purposes).
#     - db: SQLAlchemy Session object for database access.
#     Returns:
#     - A list of LearningVideoInterval objects that cover new parts of the video.
#     - A list of existing LearningVideoInterval objects that fall within the provided intervals.
#     """
#     from services.session.session_service import get_learning_sessions_by_user_and_video

#     # Retrieve all learning intervals for the user and video
#     existing_intervals = get_learning_sessions_by_user_and_video(user_id, video_id, db)

#     # Sort the existing intervals by start time to facilitate overlap checking
#     sorted_intervals = sorted(existing_intervals, key=lambda x: x.start_time)
#     # Combine the existing intervals into a single list of non-overlapping intervals
#     combined_intervals = [{'start_time': sorted_intervals[0].start_time, 'end_time': sorted_intervals[0].end_time}] if sorted_intervals else []
#     for interval in sorted_intervals[1:]:
#         if interval.start_time <= combined_intervals[-1]['end_time']:
#             # Overlapping intervals, merge them
#             combined_intervals[-1]['end_time'] = max(combined_intervals[-1]['end_time'], interval.end_time)
#         else:
#             # Non-overlapping interval, add it to the list
#             combined_intervals.append({'start_time': interval.start_time, 'end_time': interval.end_time})

#     filtered_intervals = []
#     for interval in intervals:
#         if not any(isIntervalOverlapping(interval.start_time, interval.end_time, existing['start_time'], existing['end_time']) for existing in combined_intervals):
#             filtered_intervals.append(interval)
    
#     overlapped_intervals = [existing for existing in combined_intervals for interval in filtered_intervals if isIntervalOverlapping(existing['start_time'], existing['end_time'], interval.start_time, interval.end_time)]


#     return filtered_intervals, overlapped_intervals
