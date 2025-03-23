import time
import threading
from datetime import datetime, timedelta
import heapq
from typing import Callable, Dict, List, Tuple, Optional

from util.logging_mixin import LoggingMixin


class Task:
    """
    Represents a scheduled task with timing information.
    """
    def __init__(self, func: Callable, name: str, time_str: str):
        self.func = func
        self.name = name
        self.time_str = time_str  # Format: "HH:MM"
        self.last_run = None

    def get_next_run_time(self) -> datetime:
        """
        Calculate the next time this task should run.
        """
        now = datetime.now()
        hour, minute = map(int, self.time_str.split(':'))
        
        # Create a datetime for today at the specified time
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # If that time is already past, schedule for tomorrow
        if next_run <= now:
            next_run += timedelta(days=1)
            
        return next_run


class TaskScheduler(LoggingMixin):
    """
    An efficient task scheduler that sleeps until the next task is due.
    Uses a priority queue to track upcoming tasks.
    """
    
    def __init__(self):
        """
        Initialize the scheduler.
        """
        self.running = False
        self.scheduler_thread = None
        self.tasks: Dict[str, Task] = {}
        self.task_queue: List[Tuple[datetime, str]] = []  # Priority queue (heap) of (run_time, task_name)
        self.queue_lock = threading.Lock()
        self.wakeup_event = threading.Event()
        
        self.logger.info("TaskScheduler initialized")
    
    def add_task(self, task_function: Callable, schedule_time: str, task_name: Optional[str] = None) -> str:
        """
        Add a function to be executed at the specified time daily.
        
        Args:
            task_function: Function to execute
            schedule_time: Time in format "HH:MM"
            task_name: Name for the task (defaults to function name)
            
        Returns:
            The name of the task
        """
        task_name = task_name or task_function.__name__
        
        # Create task object
        task = Task(task_function, task_name, schedule_time)
        
        with self.queue_lock:
            # Store the task
            self.tasks[task_name] = task
            
            # Calculate next run time and add to priority queue
            next_run = task.get_next_run_time()
            heapq.heappush(self.task_queue, (next_run, task_name))
            
            # If this task is scheduled sooner than current next task, wake up the scheduler
            if len(self.task_queue) == 1 or next_run < self.task_queue[0][0]:
                self.wakeup_event.set()
        
        self.logger.debug(lambda: f"Task '{task_name}' scheduled for {schedule_time} daily")
        return task_name
    
    def add_midnight_task(self, task_function: Callable, task_name: Optional[str] = None) -> str:
        """
        Add a function to be executed at midnight.
        
        Args:
            task_function: Function to execute
            task_name: Name for the task (defaults to function name)
            
        Returns:
            The name of the task
        """
        return self.add_task(task_function, "00:00", task_name)
    
    def remove_task(self, task_name: str) -> bool:
        """
        Remove a task from the scheduler.
        
        Args:
            task_name: The name of the task to remove
            
        Returns:
            True if the task was removed, False if it wasn't found
        """
        with self.queue_lock:
            if task_name in self.tasks:
                # Remove from tasks dictionary
                del self.tasks[task_name]
                
                # Rebuild priority queue (inefficient but simple)
                self.task_queue = [(run_time, name) for run_time, name in self.task_queue if name != task_name]
                heapq.heapify(self.task_queue)
                
                self.logger.debug(lambda: f"Task '{task_name}' removed from scheduler")
                return True
            
            return False
    
    def run_scheduler_loop(self):
        """
        Run the scheduler loop that sleeps until the next task is due.
        This runs in a separate thread.
        """
        self.logger.info("Scheduler loop started")
        
        while self.running:
            next_task_time = None
            next_task_name = None
            
            # Get the next task
            with self.queue_lock:
                if self.task_queue:
                    next_task_time, next_task_name = self.task_queue[0]
            
            if next_task_time is None:
                # No tasks scheduled, wait until a task is added
                self.wakeup_event.wait(60)  # Wait for up to a minute
                self.wakeup_event.clear()
                continue
            
            # Calculate how long to sleep
            now = datetime.now()
            if next_task_time > now:
                # Sleep until the next task is due (or until wakup_event is set)
                sleep_seconds = (next_task_time - now).total_seconds()
                self.logger.debug(lambda: f"Sleeping for {sleep_seconds:.1f} seconds until next task '{next_task_name}'")
                self.wakeup_event.wait(sleep_seconds)
                self.wakeup_event.clear()
                continue
            
            # Time to run a task
            with self.queue_lock:
                if not self.task_queue:
                    continue
                    
                # Double-check that the task is still due (may have changed after wakeup)
                next_task_time, next_task_name = heapq.heappop(self.task_queue)
                
                if next_task_time > datetime.now():
                    # Task is no longer due, put it back and continue
                    heapq.heappush(self.task_queue, (next_task_time, next_task_name))
                    continue
                
                # Get the task
                task = self.tasks.get(next_task_name)
                if not task:
                    continue  # Task was removed
                
                # Schedule the next run of this task
                task.last_run = datetime.now()
                next_run = task.get_next_run_time()
                heapq.heappush(self.task_queue, (next_run, next_task_name))
            
            # Execute the task (outside the lock)
            self._execute_task(task)
    
    def _execute_task(self, task: Task):
        """
        Execute a task with proper logging and error handling.
        """
        self.logger.info("Executing task '%s' at %s", task.name, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        try:
            task.func()
            self.logger.info("Task '%s' completed successfully", task.name)
        except Exception as e:
            self.logger.error("Error in task '%s': %s", task.name, str(e), exc_info=True)
    
    def start(self, run_missed: bool = False):
        """
        Start the scheduler.
        
        Args:
            run_missed: If True, run tasks that were missed (within the last 24 hours)
        """
        if self.running:
            self.logger.warning("Scheduler is already running")
            return
        
        self.running = True
        
        # Optionally run tasks that should have run recently
        if run_missed:
            now = datetime.now()
            yesterday = now - timedelta(days=1)
            
            for task_name, task in self.tasks.items():
                target_time = datetime.strptime(task.time_str, "%H:%M").time()
                target_dt = datetime.combine(now.date(), target_time)
                
                if target_dt > now:
                    continue
                
                # If the task time is today but already passed
                self.logger.info("Running missed task '%s' from today", task_name)
                self._execute_task(task)
        
        # Start scheduler in a separate thread
        self.scheduler_thread = threading.Thread(target=self.run_scheduler_loop)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
        
        self.logger.info("Scheduler started")
    
    def stop(self):
        """
        Stop the scheduler.
        """
        if not self.running:
            self.logger.warning("Scheduler is not running")
            return
        
        self.running = False
        self.wakeup_event.set()  # Wake up the scheduler thread
        
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        
        self.logger.info("Scheduler stopped")
    
    def is_running(self):
        """
        Check if the scheduler is running.
        
        Returns:
            bool: True if running, False otherwise
        """
        return self.running


# Example usage
def example_task():
    """
    Example function that will be executed at the scheduled time.
    """
    print("This is my scheduled task!")


if __name__ == "__main__":
    # Create scheduler instance
    scheduler = TaskScheduler()
    
    # Add tasks
    scheduler.add_midnight_task(example_task, "MidnightTask")
    scheduler.add_task(lambda: print("Noon check!"), "8:36", "NoonTask")
    
    try:
        # Start the scheduler
        scheduler.start()
        
        # Keep the main thread alive
        while True:
            time.sleep(60)
            
    except KeyboardInterrupt:
        print("Shutting down scheduler...")
        scheduler.stop()