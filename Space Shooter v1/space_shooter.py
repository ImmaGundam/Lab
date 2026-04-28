import curses
import random
import json
import os
import time
import sys
import traceback
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

# Game constants
PLAYER_CHAR = ">"
ENEMY_CHAR = "<"
ASTEROID_CHARS = ["(#)", "(##)", "(###)"]
MISSILE_CHAR = "-"
ENEMY_MISSILE_CHAR = "~"
SCREEN_BORDER_CHAR = "*"

# Playfield layout
# The original playfield used 26 vertical rows. This release cuts the
# active game grid in half so player/enemy/asteroid movement is tighter
# and easier to read in a terminal window.
GAME_GRID_HEIGHT = 13
PLAYABLE_TOP_ROW = 1
PLAYER_MAX_HEALTH = 50
ENEMY_MISSILE_DAMAGE = 5
COLLISION_DAMAGE = 10
HEALTH_BAR_LENGTH = 12

# Explosion animation frames
ASTEROID_EXPLOSION_FRAMES = [
    "★⭒★",  # Brighter and more visible
    "✶⁕✶",
    "*⁕*",
    "···",
    "..."
]
ENEMY_EXPLOSION_FRAMES = [
    "✺✹✺",   # Larger initial explosion
    "✺✹",
    "×+×",
    "×+",
    "··",
    "."
]

# Color constants
COLOR_PAIR_WHITE = 1
COLOR_PAIR_RED = 2
COLOR_PAIR_GREEN = 3
COLOR_PAIR_YELLOW = 4
COLOR_PAIR_BLUE = 5
COLOR_PAIR_RAINBOW = 6  # For cycling colors
COLOR_PAIR_BRIGHT_RED = 7
COLOR_PAIR_BRIGHT_YELLOW = 8
COLOR_PAIR_ASTEROID1 = 9  # Small asteroid
COLOR_PAIR_ASTEROID2 = 10  # Medium asteroid
COLOR_PAIR_ASTEROID3 = 11  # Large asteroid
COLOR_PAIR_MISSILE = 12

# Player color options
PLAYER_COLORS = {
    "White": COLOR_PAIR_WHITE,
    "Blue": COLOR_PAIR_BLUE,
    "Green": COLOR_PAIR_GREEN,
    "Yellow": COLOR_PAIR_YELLOW,
    "Rainbow": COLOR_PAIR_RAINBOW
}

# Difficulty settings with corresponding frame rates
DIFFICULTY_OPTIONS = {
    "Easy": 10,      # 10 FPS - slower, easier to play
    "Medium": 15,   # 15 FPS - moderate gameplay
    "Hard": 20      # 20 FPS - faster, more challenging
}

# Difficulty tuning
# Easy is the baseline. Medium and Hard increase hostile movement only.
# FPS values stay unchanged.
HOSTILE_SPEED_MULTIPLIERS = {
    "Easy": 1.00,
    "Medium": 1.15,
    "Hard": 1.30,
}

# Spawn intervals remain slower than the original version.
# Higher frame interval = fewer spawns.
SPAWN_INTERVAL_MULTIPLIERS = {
    "Easy": 1.30,
    "Medium": 1.30,
    "Hard": 1.30,
}

# Hostile movement speed scaling. This does not change FPS.
# Medium and Hard keep their configured FPS, but enemy ships,
# enemy missiles, and asteroids move at 70% of their previous rate.
HOSTILE_SPEED_SCALE = {
    "Easy": 1.0,
    "Medium": 0.70,
    "Hard": 0.70
}

# Spawn interval scaling. This does not change FPS.
# All difficulties reduce enemy and asteroid spawn frequency by 30%,
# so the interval is increased by roughly 1 / 0.70 = 1.43x.
SPAWN_INTERVAL_SCALE = {
    "Easy": 1.43,
    "Medium": 1.43,
    "Hard": 1.43
}

@dataclass
class Position:
    x: int
    y: int

class GameObject:
    def __init__(self, pos: Position, char: str, health: int = 1):
        self.pos = pos
        self.char = char
        self.health = health
        self.is_active = True
        self.move_accumulator_x = 0.0
        self.move_accumulator_y = 0.0
        self._move_remainder_x = 0.0
        self._move_remainder_y = 0.0

    def move_fractional(self, dx: int, dy: int, max_x: int, max_y: int, speed_scale: float = 1.0):
        """Move with fractional speed while keeping integer grid positions.

        This lets difficulty tuning slow objects down without changing the
        game's FPS or breaking terminal-cell alignment. Example: a 0.70 scale
        moves one grid cell on about 70% of frames instead of every frame.
        """
        self._move_remainder_x += dx * speed_scale
        self._move_remainder_y += dy * speed_scale

        step_x = int(abs(self._move_remainder_x))
        step_y = int(abs(self._move_remainder_y))

        if step_x:
            step_x = step_x if self._move_remainder_x > 0 else -step_x
            self._move_remainder_x -= step_x

        if step_y:
            step_y = step_y if self._move_remainder_y > 0 else -step_y
            self._move_remainder_y -= step_y

        if step_x == 0 and step_y == 0:
            return True

        return self.move(step_x, step_y, max_x, max_y)

    def move(self, dx: int, dy: int, max_x: int, max_y: int):
        new_x = self.pos.x + dx
        new_y = self.pos.y + dy
        # Enforce strict grid boundaries for the compact game grid
        if 1 <= new_x < max_x - len(self.char) and 1 <= new_y < max_y - 1:
            self.pos.x = new_x
            self.pos.y = new_y
            return True
        # Allow partial movement if only one dimension is valid
        # This ensures consistent boundary behavior across all difficulty levels
        elif 1 <= new_x < max_x - len(self.char):
            # Only X is valid, keep it but don't update Y
            self.pos.x = new_x
            return True
        elif 1 <= new_y < max_y - 1:
            # Only Y is valid, keep it but don't update X
            self.pos.y = new_y
            return True
        return False

    def take_damage(self, amount: int = 1):
        self.health -= amount
        if self.health <= 0:
            self.is_active = False


class Player(GameObject):
    def __init__(self, pos: Position, game_width: int, game_height: int, color="White", max_health=PLAYER_MAX_HEALTH):
        super().__init__(pos, PLAYER_CHAR, health=max_health)
        self.missiles: List[GameObject] = []
        self.score = 0
        self.game_width = game_width
        self.game_height = game_height
        self.color = color
        self.max_health = max_health
        self.color_frame = 0  # For rainbow effect
        
    def get_color_attr(self):
        if self.color == "Rainbow":
            # Cycle through colors for rainbow effect
            self.color_frame = (self.color_frame + 1) % 20
            if self.color_frame < 5:
                return curses.color_pair(COLOR_PAIR_RED)
            elif self.color_frame < 10:
                return curses.color_pair(COLOR_PAIR_YELLOW)
            elif self.color_frame < 15:
                return curses.color_pair(COLOR_PAIR_GREEN)
            else:
                return curses.color_pair(COLOR_PAIR_BLUE)
        else:
            return curses.color_pair(PLAYER_COLORS.get(self.color, COLOR_PAIR_WHITE))
            
    def get_health_percentage(self):
        return (self.health / self.max_health) * 100

    def fire_missile(self):
        missile_pos = Position(self.pos.x + len(self.char), self.pos.y)
        missile = GameObject(missile_pos, MISSILE_CHAR)
        # Make the missile inherit the player's color
        missile.color = self.color
        self.missiles.append(missile)

    def update_missiles(self):
        # Missile speed is FPS-dependent
        # At 60 FPS: 4 units per frame
        # At 30 FPS: 2 units per frame
        # At 10 FPS: 1 unit per frame
        missile_speed = max(1, 4 * (self.game_width // 140))  # Scale based on screen width
        for missile in self.missiles:
            moved = missile.move(missile_speed, 0, self.game_width, self.game_height)
            # Delete missiles once they leave or touch the right edge.
            if not moved or missile.pos.x >= self.game_width - len(missile.char) - 1:
                missile.is_active = False

        # Remove inactive missiles from memory/runtime lists.
        self.missiles = [m for m in self.missiles if m.is_active]


class Enemy(GameObject):
    def __init__(self, pos: Position, game_width: int, game_height: int, speed_multiplier: float = 1.0):
        super().__init__(pos, ENEMY_CHAR)
        self.missiles: List[GameObject] = []
        self.game_width = game_width
        self.game_height = game_height
        self.speed_multiplier = speed_multiplier
        self.fire_cooldown = random.randint(10, 30)
        self.current_cooldown = self.fire_cooldown

    def update(self, speed_scale: float = 1.0):
        # Enemy speed depends on screen width, then difficulty scaling is applied
        # through fractional grid movement so FPS stays unchanged.
        enemy_speed = max(1, 2 * (self.game_width // 140))
        moved = self.move_fractional(-enemy_speed, 0, self.game_width, self.game_height, speed_scale)
        # Delete enemies as soon as they touch the left side of the game view.
        if not moved or self.pos.x <= 1:
            self.is_active = False
            return

        # Update fire cooldown
        self.current_cooldown -= 1
        if self.current_cooldown <= 0:
            self.fire_missile()
            self.current_cooldown = self.fire_cooldown

    def fire_missile(self):
        missile_pos = Position(self.pos.x - 1, self.pos.y)
        missile = GameObject(missile_pos, ENEMY_MISSILE_CHAR)
        self.missiles.append(missile)

    def update_missiles(self, speed_scale: float = 1.0):
        # Enemy missile speed depends on screen width, then difficulty scaling is
        # applied through fractional grid movement so FPS stays unchanged.
        missile_speed = max(1, 3 * (self.game_width // 140))
        for missile in self.missiles:
            moved = missile.move_fractional(-missile_speed, 0, self.game_width, self.game_height, speed_scale)
            # Delete enemy missiles once they touch the left side of the view.
            if not moved or missile.pos.x <= 1:
                missile.is_active = False

        # Remove inactive missiles from memory/runtime lists.
        self.missiles = [m for m in self.missiles if m.is_active]


class Asteroid(GameObject):
    def __init__(self, pos: Position, size: int, game_width: int, game_height: int, speed_multiplier: float = 1.0):
        self.size = size  # 1, 2, or 3
        char = ASTEROID_CHARS[size - 1]
        super().__init__(pos, char, health=size)
        self.game_width = game_width
        self.game_height = game_height
        self.speed_multiplier = speed_multiplier
        self.velocity = random.choice([-1, 0, 1])

    def update(self, speed_scale: float = 1.0):
        # Asteroid speed depends on screen width, then difficulty scaling is
        # applied through fractional grid movement so FPS stays unchanged.
        asteroid_speed = max(1, 2 * (self.game_width // 140))
        # Keep vertical drift to one grid row so asteroids stay aligned with the
        # same compact row system as the player and enemies.
        velocity_factor = 1
        moved = self.move_fractional(-asteroid_speed, self.velocity * velocity_factor, self.game_width, self.game_height, speed_scale)
        # Delete asteroids as soon as they touch the left side of the game view.
        if not moved or self.pos.x <= 1:
            self.is_active = False


class ParticleEffect:
    def __init__(self, pos: Position, effect_type: str, size: int = 1):
        self.pos = pos
        self.type = effect_type  # "asteroid" or "enemy"
        self.size = size  # Size of the original object (for asteroids)
        self.frame = 0
        self.max_frames = len(ASTEROID_EXPLOSION_FRAMES) if effect_type == "asteroid" else len(ENEMY_EXPLOSION_FRAMES)
        self.is_active = True
        self.frame_delay = 12  # Slower animation for better visibility at 60 FPS
        self.frame_counter = 0
        
    def update(self):
        self.frame_counter += 1
        if self.frame_counter >= self.frame_delay:
            self.frame_counter = 0
            self.frame += 1
            if self.frame >= self.max_frames:
                self.is_active = False
    
    def get_current_frame(self):
        if not self.is_active:
            return ""
            
        if self.type == "asteroid":
            frames = ASTEROID_EXPLOSION_FRAMES
            # Scale the frame based on original asteroid size
            if self.size == 1:
                return frames[self.frame][0] if self.frame < len(frames) else ""
            elif self.size == 2:
                return frames[self.frame][:2] if self.frame < len(frames) else ""
            else:
                return frames[self.frame] if self.frame < len(frames) else ""
        else:  # enemy
            frames = ENEMY_EXPLOSION_FRAMES
            return frames[self.frame] if self.frame < len(frames) else ""


class ScoreBoard:
    def __init__(self, file_path: str = "scoreboard.json"):
        self.file_path = file_path
        self.scores = []
        try:
            self.load_scores()
        except Exception as e:
            print(f"Error loading scoreboard: {e}", file=sys.stderr)
            # Initialize with empty scoreboard
            self.scores = []

    def load_scores(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r') as f:
                    self.scores = json.load(f)
            except:
                self.scores = []
        else:
            self.scores = []

    def save_scores(self):
        try:
            # Create a temporary file first
            temp_path = f"{self.file_path}.tmp"
            with open(temp_path, 'w') as f:
                json.dump(self.scores, f)
                
            # Only after successful write, replace the original file
            if os.path.exists(temp_path):
                if os.path.exists(self.file_path):
                    try:
                        os.remove(self.file_path)
                    except:
                        pass
                os.rename(temp_path, self.file_path)
        except Exception as e:
            print(f"Error saving scoreboard: {e}", file=sys.stderr)

    def add_score(self, player_name: str, score: int):
        self.scores.append({"name": player_name, "score": score, "date": time.strftime("%Y-%m-%d %H:%M")})
        # Sort by score (highest first) and keep only top 10
        self.scores = sorted(self.scores, key=lambda x: x["score"], reverse=True)[:10]
        self.save_scores()

    def clear_scores(self):
        self.scores = []
        self.save_scores()

    def get_scores(self):
        return self.scores


class Settings:
    def __init__(self, file_path: str = "settings.json"):
        self.file_path = file_path
        self.settings = {
            "player_name": "guest",
            "player_color": "White",
            "difficulty": "Easy",
            "attempt_number": 1
        }
        self.load_settings()

    def load_settings(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r') as f:
                    self.settings = json.load(f)
            except:
                pass

    def save_settings(self):
        with open(self.file_path, 'w') as f:
            json.dump(self.settings, f)

    def get_player_name(self):
        if self.settings.get("player_name") == "guest":
            return f"guest{self.settings.get('attempt_number', 1)}"
        return self.settings.get("player_name", "guest")

    def set_player_name(self, name: str):
        self.settings["player_name"] = name
        self.save_settings()

    def get_player_color(self):
        return self.settings.get("player_color", "White")

    def set_player_color(self, color: str):
        if color in PLAYER_COLORS:
            self.settings["player_color"] = color
            self.save_settings()

    def get_difficulty(self):
        """Get the difficulty setting"""
        difficulty = self.settings.get("difficulty", "Easy")
        return difficulty
    
    def get_fps_for_difficulty(self):
        """Get the frame rate for the current difficulty setting"""
        difficulty = self.get_difficulty()
        return DIFFICULTY_OPTIONS.get(difficulty, 10)  # Default to Easy (10 FPS)

    def get_hostile_speed_scale(self):
        """Get enemy/asteroid movement scaling without changing FPS."""
        difficulty = self.get_difficulty()
        return HOSTILE_SPEED_SCALE.get(difficulty, 1.0)

    def get_spawn_interval_scale(self):
        """Get spawn interval scaling without changing FPS."""
        difficulty = self.get_difficulty()
        return SPAWN_INTERVAL_SCALE.get(difficulty, 1.0)
    
    def get_hostile_speed_multiplier(self):
        """Get hostile movement multiplier for the current difficulty.

        Easy is the baseline. Medium is +15%. Hard is +30%.
        FPS does not change.
        """
        difficulty = self.get_difficulty()
        return HOSTILE_SPEED_MULTIPLIERS.get(difficulty, 1.0)

    def get_spawn_interval_multiplier(self):
        """Get spawn interval multiplier for the current difficulty."""
        difficulty = self.get_difficulty()
        return SPAWN_INTERVAL_MULTIPLIERS.get(difficulty, 1.30)

    def set_difficulty(self, difficulty):
        """Set the difficulty level"""
        if difficulty in DIFFICULTY_OPTIONS:
            self.settings["difficulty"] = difficulty
            fps = DIFFICULTY_OPTIONS[difficulty]
            print(f"Setting difficulty to {difficulty} ({fps} FPS)", file=sys.stderr)
            # Note: This will take effect next time a game is started
            self.save_settings()

    def increment_attempt(self):
        self.settings["attempt_number"] = self.settings.get("attempt_number", 1) + 1
        self.save_settings()


class Game:
    def __init__(self, stdscr):
        print("Initializing game...", file=sys.stderr)
        self.stdscr = stdscr
        # Get terminal width and use a compact fixed-height playfield.
        # A fixed grid keeps player, enemy, asteroid, and projectile rows aligned
        # across all difficulty levels.
        orig_height, self.width = stdscr.getmaxyx()
        print(f"Terminal size: {self.width}x{orig_height}", file=sys.stderr)
        self.height = min(GAME_GRID_HEIGHT, max(8, orig_height - 2))
        self.width -= 2  # Still reduce width to avoid boundary issues
        print(f"Game area size: {self.width}x{self.height}", file=sys.stderr)
        self.player = None
        self.enemies = []
        self.asteroids = []
        self.particles = []  # For explosion effects
        self.running = True
        self.scoreboard = ScoreBoard()
        self.settings = Settings()
        self.hostile_speed_multiplier = self.settings.get_hostile_speed_multiplier()
        self.game_over = False
        self.paused = False
        self.return_to_menu = False
        self.score = 0
        self.base_enemy_spawn_rate = 30
        self.base_asteroid_spawn_rate = 20
        spawn_interval_scale = self.settings.get_spawn_interval_scale()
        self.enemy_spawn_rate = max(1, round(self.base_enemy_spawn_rate * spawn_interval_scale))
        self.asteroid_spawn_rate = max(1, round(self.base_asteroid_spawn_rate * spawn_interval_scale))
        self.frame_counter = 0
        self.last_frame_time = time.time()
        self.target_fps = self.settings.get_fps_for_difficulty()  # Set FPS based on difficulty
        self.apply_difficulty_tuning()
        self.hostile_speed_scale = self.settings.get_hostile_speed_scale()
        # Input handling - simplified tracking
        self.last_key_press = {}        # Dictionary to track last press time for fire key only
        self.key_states = {}            # Dictionary to track which keys are pressed (for UI feedback)
        self.last_handled_key = None    # The last key we processed
        self.input_initialized = False  # Track if input has been initialized

        # Reset and clean input state
        self.reset_input_state()
        
        # Fire cooldown is time-based and consistent across all difficulties.
        # This keeps player firing speed from feeling slower when FPS changes.
        self.fire_key_delay = 0.18
        
        # Remove movement delay completely
        self.movement_key_delay = 0.0
        
        print(f"Game initialized with difficulty: {self.settings.get_difficulty()} ({self.target_fps} FPS)", file=sys.stderr)

    def apply_difficulty_tuning(self):
        """Apply difficulty tuning without changing FPS.

        Easy is the baseline.
        Medium hostile movement = Easy + 15%.
        Hard hostile movement = Easy + 30%.
        Spawn intervals are kept slower for all difficulties.
        """
        self.hostile_speed_multiplier = self.settings.get_hostile_speed_multiplier()
        spawn_multiplier = self.settings.get_spawn_interval_multiplier()
        self.enemy_spawn_rate = max(1, int(round(30 * spawn_multiplier)))
        self.asteroid_spawn_rate = max(1, int(round(20 * spawn_multiplier)))

    def reset_input_state(self):
        """Reset and clean input state to ensure proper handling after transitions"""
        try:
            # Clear any pending input
            curses.flushinp()
            
            # Reset terminal input mode
            self.stdscr.nodelay(True)
            self.stdscr.timeout(0)
            
            # Ensure keyboard mode is properly set
            self.stdscr.keypad(True)
            
            # Reset input tracking
            self.last_key_press = {}
            self.key_states = {}
            self.last_handled_key = None
            self.input_initialized = True
            
            print("Input state reset successfully", file=sys.stderr)
        except Exception as e:
            print(f"Error resetting input state: {e}", file=sys.stderr)

    def playable_bottom_row(self):
        """Last usable row inside the border."""
        return self.height - 2

    def playable_rows(self):
        """Rows that all active game objects are allowed to use."""
        return list(range(PLAYABLE_TOP_ROW, self.playable_bottom_row() + 1))

    def clamp_to_playfield_row(self, y):
        """Keep objects on the same compact vertical grid."""
        return max(PLAYABLE_TOP_ROW, min(self.playable_bottom_row(), y))

    def setup(self):
        curses.curs_set(0)  # Hide cursor
        curses.noecho()
        curses.cbreak()
        self.stdscr.keypad(True)
        
        # Force raw input mode for maximum responsiveness
        try:
            curses.raw()
        except:
            pass
        
        try:
            os.nice(-10)  # Try to increase process priority
        except:
            pass
        
        # Set up colors if available
        if curses.has_colors():
            curses.start_color()
            # Attempt to use extended color pairs if available
            try:
                curses.use_default_colors()  # Try to use terminal default colors for better contrast
            except:
                pass
                
            # Basic colors
            curses.init_pair(COLOR_PAIR_WHITE, curses.COLOR_WHITE, curses.COLOR_BLACK)
            curses.init_pair(COLOR_PAIR_RED, curses.COLOR_RED, curses.COLOR_BLACK)
            curses.init_pair(COLOR_PAIR_GREEN, curses.COLOR_GREEN, curses.COLOR_BLACK)
            curses.init_pair(COLOR_PAIR_YELLOW, curses.COLOR_YELLOW, curses.COLOR_BLACK)
            curses.init_pair(COLOR_PAIR_BLUE, curses.COLOR_BLUE, curses.COLOR_BLACK)
            
            # Enhanced colors - using bold attribute to simulate brightness
            curses.init_pair(COLOR_PAIR_BRIGHT_RED, curses.COLOR_RED, curses.COLOR_BLACK)
            curses.init_pair(COLOR_PAIR_BRIGHT_YELLOW, curses.COLOR_YELLOW, curses.COLOR_BLACK)
            
            # Asteroid colors
            curses.init_pair(COLOR_PAIR_ASTEROID1, curses.COLOR_WHITE, curses.COLOR_BLACK)  # Small
            curses.init_pair(COLOR_PAIR_ASTEROID2, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Medium
            curses.init_pair(COLOR_PAIR_ASTEROID3, curses.COLOR_RED, curses.COLOR_BLACK)  # Large
            
            # Missile color
            curses.init_pair(COLOR_PAIR_MISSILE, curses.COLOR_CYAN, curses.COLOR_BLACK)
            
        # Initial player position on the compact shared grid
        player_pos = Position(5, self.clamp_to_playfield_row(self.height // 2))
        player_color = self.settings.get_player_color()
        self.player = Player(player_pos, self.width, self.height, color=player_color, max_health=PLAYER_MAX_HEALTH)
        
        # Update difficulty setting
        self.target_fps = self.settings.get_fps_for_difficulty()
        self.hostile_speed_scale = self.settings.get_hostile_speed_scale()
        spawn_interval_scale = self.settings.get_spawn_interval_scale()
        self.enemy_spawn_rate = max(1, round(self.base_enemy_spawn_rate * spawn_interval_scale))
        self.asteroid_spawn_rate = max(1, round(self.base_asteroid_spawn_rate * spawn_interval_scale))
        difficulty = self.settings.get_difficulty()
        # IMPORTANT: vertical grid is compact and fixed regardless of difficulty level
        # Vertical movement is consistent at one grid cell per keypress across ALL difficulties
        # Recalculate key delays based on selected difficulty
        self.apply_difficulty_tuning()
        difficulty_factor = 30.0 / max(1, self.target_fps)
        base_fire_delay = 0.25      # Base delay for Medium
        
        # Movement should always be immediate regardless of difficulty
        self.movement_key_delay = 0.0
        
        # Fire cooldown is time-based and consistent across all difficulties.
        # This keeps player firing speed from feeling slower when FPS changes.
        self.fire_key_delay = 0.18

    def safe_addstr(self, y, x, text, attr=0, is_game_object=False):
        """Safe function to draw text with boundary checking"""
        try:
            # Don't write to the bottom-right corner
            if y == self.height - 1 and x + len(text) >= self.width - 1:
                text = text[:self.width - x - 1]
                
            if not text:  # Skip empty text
                return
                
            # Draw the text
            self.stdscr.addstr(y, x, text, attr)
        except:
            pass  # Silently ignore curses errors

    def draw_border(self):
        # Draw top and bottom borders
        for x in range(self.width):
            self.safe_addstr(0, x, SCREEN_BORDER_CHAR)
            # Avoid writing to the very last cell
            if x < self.width - 1:
                self.safe_addstr(self.height - 1, x, SCREEN_BORDER_CHAR)
        
        # Draw left and right borders
        for y in range(self.height):
            self.safe_addstr(y, 0, SCREEN_BORDER_CHAR)
            # Don't write to the bottom-right corner
            if y < self.height - 1:
                self.safe_addstr(y, self.width - 1, SCREEN_BORDER_CHAR)

    def draw_game_objects(self):
        # Clear screen
        self.stdscr.clear()
        
        # Draw border
        self.draw_border()
        
        # Draw player
        if self.player and self.player.is_active:
            player_attr = 0
            if curses.has_colors():
                player_attr = self.player.get_color_attr()
                
            # Draw the player character
            self.safe_addstr(self.player.pos.y, self.player.pos.x, self.player.char, player_attr)
        
        # Draw player missiles
        if self.player:
            for missile in self.player.missiles:
                if missile.is_active:
                    missile_attr = curses.color_pair(COLOR_PAIR_MISSILE)
                    if hasattr(missile, 'color') and missile.color == "Rainbow":
                        # For rainbow player, use matching missile color
                        missile_attr = self.player.get_color_attr()
                    
                    # Draw the missile
                    self.safe_addstr(missile.pos.y, missile.pos.x, missile.char, missile_attr | curses.A_BOLD)
        
        # Draw enemies and their missiles
        for enemy in self.enemies:
            if enemy.is_active:
                enemy_attr = 0
                if curses.has_colors():
                    enemy_attr = curses.color_pair(COLOR_PAIR_BRIGHT_RED) | curses.A_BOLD
                
                # Draw the enemy
                self.safe_addstr(enemy.pos.y, enemy.pos.x, enemy.char, enemy_attr)
                for missile in enemy.missiles:
                    if missile.is_active:
                        # Draw the enemy missile
                        self.safe_addstr(missile.pos.y, missile.pos.x, missile.char, 0)
        
        # Draw asteroids
        for asteroid in self.asteroids:
            if asteroid.is_active:
                asteroid_attr = 0
                if curses.has_colors():
                    # Different colors based on asteroid size
                    if asteroid.size == 1:
                        asteroid_attr = curses.color_pair(COLOR_PAIR_ASTEROID1)
                    elif asteroid.size == 2:
                        asteroid_attr = curses.color_pair(COLOR_PAIR_ASTEROID2)
                    else:
                        asteroid_attr = curses.color_pair(COLOR_PAIR_ASTEROID3)
                
                # Draw the asteroid
                self.safe_addstr(asteroid.pos.y, asteroid.pos.x, asteroid.char, asteroid_attr)
        
        # Draw particles (explosion effects)
        for particle in self.particles:
            if particle.is_active:
                frame = particle.get_current_frame()
                color_attr = 0
                if curses.has_colors():
                    # Make explosion effect color vary by frame for more dynamic effect
                    if particle.type == "asteroid":
                        if particle.frame == 0:
                            color_attr = curses.color_pair(COLOR_PAIR_BRIGHT_YELLOW) | curses.A_BOLD | curses.A_BLINK
                        elif particle.frame == 1:
                            color_attr = curses.color_pair(COLOR_PAIR_BRIGHT_YELLOW) | curses.A_BOLD
                        else:
                            color_attr = curses.color_pair(COLOR_PAIR_YELLOW)
                    else:  # enemy
                        if particle.frame == 0:
                            color_attr = curses.color_pair(COLOR_PAIR_BRIGHT_RED) | curses.A_BOLD | curses.A_BLINK
                        elif particle.frame < 3:
                            color_attr = curses.color_pair(COLOR_PAIR_BRIGHT_RED) | curses.A_BOLD
                        else:
                            color_attr = curses.color_pair(COLOR_PAIR_RED)
                # Draw the particle effect
                self.safe_addstr(particle.pos.y, particle.pos.x, frame, color_attr)
        
        # Draw score, difficulty, and health bar
        score_text = f"Score: {self.score}"
        self.safe_addstr(0, 2, score_text)

        difficulty_text = f"Difficulty: {self.settings.get_difficulty()}"
        difficulty_x = min(self.width - len(difficulty_text) - 2, 14)
        if difficulty_x > 2:
            self.safe_addstr(0, difficulty_x, difficulty_text)

        # Draw health bar
        if self.player:
            health_percent = self.player.get_health_percentage()
            health_text = f"Health: {health_percent:.0f}% "
            health_bar_length = HEALTH_BAR_LENGTH
            filled_length = int(health_bar_length * health_percent / 100)
            
            # Choose color based on health percentage
            health_color = 0
            if curses.has_colors():
                if health_percent > 70:
                    health_color = curses.color_pair(COLOR_PAIR_GREEN)
                elif health_percent > 40:
                    health_color = curses.color_pair(COLOR_PAIR_YELLOW)
                else:
                    health_color = curses.color_pair(COLOR_PAIR_RED)
            
            # Draw health text
            health_x = self.width - len(health_text) - health_bar_length - 4
            self.safe_addstr(0, health_x, health_text, curses.A_BOLD)
            
            # Draw health bar with bolder characters
            for i in range(health_bar_length):
                if i < filled_length:
                    bar_char = "█"
                    # Make critical health more noticeable with flashing
                    bar_attr = health_color
                    if health_percent <= 20 and self.frame_counter % 10 < 5:
                        bar_attr |= curses.A_BOLD | curses.A_BLINK
                    self.safe_addstr(0, health_x + len(health_text) + i, bar_char, bar_attr)
                else:
                    self.safe_addstr(0, health_x + len(health_text) + i, "░")
        
        # Game status information in bottom corner
        if not self.game_over:
            controls_text = "Controls: WASD/Arrows to move, Space to fire, ESC to pause"
            self.safe_addstr(self.height - 1, 2, controls_text)

    def draw_pause_menu(self):
        # Draw dark overlay for pause menu background
        for y in range(1, self.height - 1):
            overlay_text = " " * (self.width - 2)
            self.safe_addstr(y, 1, overlay_text, curses.A_DIM)
        
        # Draw pause box
        box_width = 40
        box_height = 9
        box_x = (self.width - box_width) // 2
        box_y = (self.height - box_height) // 2
        
        # Draw box with solid background for better contrast
        for y in range(box_y, box_y + box_height):
            if y == box_y:
                self.safe_addstr(y, box_x, "┌" + "─" * (box_width - 2) + "┐", curses.A_BOLD)
            elif y == box_y + box_height - 1:
                self.safe_addstr(y, box_x, "└" + "─" * (box_width - 2) + "┘", curses.A_BOLD)
            else:
                # Fill box with dark background
                self.safe_addstr(y, box_x, "│" + " " * (box_width - 2) + "│", curses.A_BOLD)
        
        # Draw messages with background highlight
        pause_text = "GAME PAUSED"
        resume_text = "Press ESC to resume"
        menu_text = "Press M for Main Menu"
        
        # Center text in box
        pause_attr = curses.A_BOLD
        if self.frame_counter % 10 < 5:  # Blink effect for pause text
            pause_attr |= curses.A_REVERSE
            
        self.safe_addstr(box_y + 2, box_x + (box_width - len(pause_text)) // 2, pause_text, pause_attr)
        self.safe_addstr(box_y + 4, box_x + (box_width - len(resume_text)) // 2, resume_text)
        self.safe_addstr(box_y + 6, box_x + (box_width - len(menu_text)) // 2, menu_text)
        
        # Refresh screen
        self.stdscr.refresh()
    
    def handle_input(self):
        try:
            # Ensure input state is initialized
            if not self.input_initialized:
                self.reset_input_state()

            # Process all available keys immediately
            key_count = 0
            while True:
                key = self.stdscr.getch()
                if key == -1:  # No more keys
                    break
                    
                key_count += 1
                # Process key immediately
                if not self.paused:
                    self.process_key(key)
                else:
                    # Always handle pause menu keys
                    if key == 27 or key == ord('m') or key == ord('M') or key == 10:  # Added Enter key (10)
                        self.process_key(key)
            
            # Force screen refresh if we processed keys for immediate feedback regardless of difficulty
            if key_count > 0 and self.player and not self.paused:
                self.stdscr.refresh()
                
            # Only clear input buffer if we've accumulated a lot of events or periodically
            if key_count > 10 or self.frame_counter % 60 == 0:
                curses.flushinp()
                
        except Exception as e:
            print(f"Input handling error: {e}", file=sys.stderr)
            # Reset input state on error to prevent cascading issues
            self.reset_input_state()
        
        return self.last_handled_key
        
    def process_key(self, key):
        # Store key for debugging
        self.last_handled_key = key
        
        # Handle pause toggle immediately
        if key == 27:  # ESC key
            self.paused = not self.paused
            curses.flushinp()
            return

        # If paused, only handle menu keys
        if self.paused:
            if key == ord('m') or key == ord('M'):
                self.return_to_menu = True
                self.running = False
            return

        # Process movement and fire keys
        key_map = {
            curses.KEY_UP: ('up', 0, -1),
            ord('w'): ('up', 0, -1),
            ord('W'): ('up', 0, -1),
            curses.KEY_DOWN: ('down', 0, 1),
            ord('s'): ('down', 0, 1),
            ord('S'): ('down', 0, 1),
            curses.KEY_LEFT: ('left', -1, 0),
            ord('a'): ('left', -1, 0),
            ord('A'): ('left', -1, 0),
            curses.KEY_RIGHT: ('right', 1, 0),
            ord('d'): ('right', 1, 0),
            ord('D'): ('right', 1, 0),
            ord(' '): ('fire', 0, 0)
        }
        
        if key in key_map:
            key_id, dx, dy = key_map[key]
            current_time = time.time()
            
            if key_id == 'fire':
                # Keep fire rate limiting for game balance
                last_press = self.last_key_press.get(key_id, 0)
                if current_time - last_press >= self.fire_key_delay:
                    self.player.fire_missile()
                    self.last_key_press[key_id] = current_time
            else:
                # Process EXACTLY one grid cell movement per keypress
                # Movement is identical across ALL difficulty levels
                # This ensures consistent compact vertical grid behavior
                self.player.move(dx, dy, self.width, self.height)
                
                # No difficulty-specific movement code
                # No speed multipliers
                # Every difficulty level moves exactly one grid cell per keypress
        
        return key

    def spawn_enemies_and_asteroids(self):
        # Spawn enemies fully inside the right border so they do not get
        # caught on the edge before entering the playfield.
        if self.frame_counter % self.enemy_spawn_rate == 0:
            y = random.choice(self.playable_rows())
            enemy_x = self.width - len(ENEMY_CHAR) - 1
            enemy_pos = Position(enemy_x, y)
            self.enemies.append(Enemy(enemy_pos, self.width, self.height, self.hostile_speed_multiplier))

        # Spawn asteroids fully inside the right border. Larger asteroid
        # sprites need more horizontal space than enemies.
        if self.frame_counter % self.asteroid_spawn_rate == 0:
            y = random.choice(self.playable_rows())
            size = random.randint(1, 3)
            asteroid_char = ASTEROID_CHARS[size - 1]
            asteroid_x = self.width - len(asteroid_char) - 1
            asteroid_pos = Position(asteroid_x, y)
            self.asteroids.append(Asteroid(asteroid_pos, size, self.width, self.height, self.hostile_speed_multiplier))

    def check_collisions(self):
        # Player missiles vs enemies
        for missile in self.player.missiles[:]:
            for enemy in self.enemies[:]:
                if (enemy.is_active and missile.is_active and 
                    missile.pos.x >= enemy.pos.x and 
                    missile.pos.x <= enemy.pos.x + len(enemy.char) and
                    missile.pos.y == enemy.pos.y):
                    enemy.take_damage()
                    missile.is_active = False
                    if not enemy.is_active:
                        # Create explosion effect at enemy position
                        self.particles.append(ParticleEffect(Position(enemy.pos.x, enemy.pos.y), "enemy"))
                        self.score += 10
        
        # Player missiles vs asteroids
        for missile in self.player.missiles[:]:
            for asteroid in self.asteroids[:]:
                if (asteroid.is_active and missile.is_active and 
                    missile.pos.x >= asteroid.pos.x and 
                    missile.pos.x <= asteroid.pos.x + len(asteroid.char) and
                    missile.pos.y == asteroid.pos.y):
                    asteroid.take_damage()
                    missile.is_active = False
                    if not asteroid.is_active:
                        # Create explosion effect at asteroid position
                        self.particles.append(ParticleEffect(Position(asteroid.pos.x, asteroid.pos.y), "asteroid", asteroid.size))
                        self.score += 5 * asteroid.size
        
        # Enemy missiles vs player
        for enemy in self.enemies:
            for missile in enemy.missiles[:]:
                if (self.player.is_active and missile.is_active and 
                    missile.pos.x >= self.player.pos.x and 
                    missile.pos.x <= self.player.pos.x + len(self.player.char) and
                    missile.pos.y == self.player.pos.y):
                    self.player.take_damage(ENEMY_MISSILE_DAMAGE)
                    missile.is_active = False
                    if not self.player.is_active:
                        self.game_over = True
        
        # Player vs enemies and asteroids
        if self.player.is_active:
            # Check collision with enemies
            for enemy in self.enemies:
                if (enemy.is_active and 
                    ((enemy.pos.x <= self.player.pos.x <= enemy.pos.x + len(enemy.char) and enemy.pos.y == self.player.pos.y) or
                     (self.player.pos.x <= enemy.pos.x <= self.player.pos.x + len(self.player.char) and enemy.pos.y == self.player.pos.y))):
                    self.player.take_damage(COLLISION_DAMAGE)
                    enemy.take_damage()
                    if not enemy.is_active:
                        # Create explosion effect at enemy position
                        self.particles.append(ParticleEffect(Position(enemy.pos.x, enemy.pos.y), "enemy"))
                    if not self.player.is_active:
                        self.game_over = True
            
            # Check collision with asteroids
            for asteroid in self.asteroids:
                if (asteroid.is_active and 
                    ((asteroid.pos.x <= self.player.pos.x <= asteroid.pos.x + len(asteroid.char) and asteroid.pos.y == self.player.pos.y) or
                     (self.player.pos.x <= asteroid.pos.x <= self.player.pos.x + len(self.player.char) and asteroid.pos.y == self.player.pos.y))):
                    self.player.take_damage(COLLISION_DAMAGE)
                    asteroid.take_damage()
                    if not asteroid.is_active:
                        # Create explosion effect at asteroid position
                        self.particles.append(ParticleEffect(Position(asteroid.pos.x, asteroid.pos.y), "asteroid", asteroid.size))
                    if not self.player.is_active:
                        self.game_over = True

    def update(self):
        if self.paused:
            return
            
        # Update game state
        self.frame_counter += 1
        
        # Update player missiles
        if self.player:
            self.player.game_width = self.width
            self.player.game_height = self.height
            self.player.update_missiles()
        
        # Update enemies
        for enemy in self.enemies[:]:
            if enemy.is_active:
                enemy.update(self.hostile_speed_scale)
                enemy.update_missiles(self.hostile_speed_scale)
            else:
                self.enemies.remove(enemy)
        
        # Update asteroids
        for asteroid in self.asteroids[:]:
            if asteroid.is_active:
                asteroid.update(self.hostile_speed_scale)
            else:
                self.asteroids.remove(asteroid)
                
        # Update particle effects
        for particle in self.particles[:]:
            if particle.is_active:
                particle.update()
            else:
                self.particles.remove(particle)
        
        # Check for collisions
        self.check_collisions()
        
        # Spawn new enemies and asteroids
        self.spawn_enemies_and_asteroids()
        
        # Clean up off-screen/inactive objects so runtime lists cannot grow.
        # Objects are deleted once they touch the left side of the game view.
        self.enemies = [e for e in self.enemies if e.is_active and e.pos.x > 1]
        self.asteroids = [a for a in self.asteroids if a.is_active and a.pos.x > 1]
        if self.player:
            self.player.missiles = [m for m in self.player.missiles if m.is_active]
        for enemy in self.enemies:
            enemy.missiles = [m for m in enemy.missiles if m.is_active]
        
        # Update frame timing
        self.last_frame_time = time.time()

    def run_game(self):
        """Main game loop that handles rendering, input, and game state updates"""
        try:
            # Initialize game
            self.setup()
            self.reset_input_state()  # Ensure clean input state
            self.running = True
            self.game_over = False
            self.return_to_menu = False
            
            # Main game loop
            while self.running:
                # Target frame time based on FPS (e.g., 60 FPS = 1/60 = 0.0167 seconds per frame)
                target_frame_time = 1.0 / self.target_fps
                frame_start_time = time.time()
                
                # Process input
                self.handle_input()
                
                # Return to menu if requested
                if self.return_to_menu:
                    break
                
                # Update game state if not paused
                if not self.paused:
                    self.update()
                
                # Draw game
                self.draw_game_objects()
                
                # If paused, draw pause menu
                if self.paused:
                    self.draw_pause_menu()
                
                # If game over, show game over screen and handle high score
                if self.game_over:
                    self.show_game_over()
                    break
                
                # Refresh screen
                self.stdscr.refresh()
                
                # Calculate elapsed time and sleep if needed to maintain target frame rate
                elapsed = time.time() - frame_start_time
                sleep_time = max(0, target_frame_time - elapsed)
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
            
            # Save score if game ended normally
            if self.game_over:
                player_name = self.settings.get_player_name()
                self.scoreboard.add_score(player_name, self.score)
                self.settings.increment_attempt()
            
            # Clean up game state and reset terminal for menu
            self.cleanup_game_state()
        
        except Exception as e:
            print(f"Error in run_game: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            self.running = False
            # Try to clean up even after error
            try:
                self.cleanup_game_state()
            except:
                pass
    
    def cleanup_game_state(self):
        """Clean up game state and prepare terminal for menu"""
        try:
            # Reset terminal settings
            self.stdscr.clear()
            self.stdscr.refresh()
            
            # Clear input state
            curses.flushinp()
            self.stdscr.nodelay(False)
            self.stdscr.timeout(-1)  # Switch back to blocking mode for menu
            
            # Reset tracking variables
            self.input_initialized = False
            self.last_key_press = {}
            self.key_states = {}
            
            # Save any pending scores/settings
            if hasattr(self, 'settings') and self.settings:
                try:
                    self.settings.save_settings()
                except Exception as e:
                    print(f"Error saving settings: {e}", file=sys.stderr)
                    
            if hasattr(self, 'scoreboard') and self.scoreboard:
                try:
                    self.scoreboard.save_scores()
                except Exception as e:
                    print(f"Error saving scoreboard: {e}", file=sys.stderr)
                    
            print("Game state cleaned up successfully", file=sys.stderr)
        except Exception as e:
            print(f"Error during cleanup: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
    def show_game_over(self):
        """Display game over screen with score"""
        # Draw dark overlay
        for y in range(1, self.height - 1):
            overlay_text = " " * (self.width - 2)
            self.safe_addstr(y, 1, overlay_text, curses.A_DIM)
        
        # Draw game over box
        box_width = 40
        box_height = 7
        box_x = (self.width - box_width) // 2
        box_y = (self.height - box_height) // 2
        
        # Draw box
        for y in range(box_y, box_y + box_height):
            if y == box_y:
                self.safe_addstr(y, box_x, "┌" + "─" * (box_width - 2) + "┐", curses.A_BOLD)
            elif y == box_y + box_height - 1:
                self.safe_addstr(y, box_x, "└" + "─" * (box_width - 2) + "┘", curses.A_BOLD)
            else:
                self.safe_addstr(y, box_x, "│" + " " * (box_width - 2) + "│", curses.A_BOLD)
        
        # Draw messages
        game_over_text = "GAME OVER"
        score_text = f"Final Score: {self.score}"
        continue_text = "Press any key to continue"
        
        # Game over with flashing effect
        game_over_attr = curses.A_BOLD
        if self.frame_counter % 10 < 5:  # Blink effect
            game_over_attr |= curses.A_REVERSE
            
        # Center and display text
        self.safe_addstr(box_y + 2, box_x + (box_width - len(game_over_text)) // 2, game_over_text, game_over_attr)
        self.safe_addstr(box_y + 3, box_x + (box_width - len(score_text)) // 2, score_text, curses.A_BOLD)
        self.safe_addstr(box_y + 5, box_x + (box_width - len(continue_text)) // 2, continue_text)
        
        # Refresh and wait for key press
        self.stdscr.refresh()
        
        # Wait a moment before accepting input to prevent accidental skipping
        curses.napms(500)
        self.stdscr.timeout(-1)  # Switch to blocking mode for key press
        
        # Clear input buffer
        curses.flushinp()
        
        # Wait for key press
        self.stdscr.getch()
        
        # Reset to non-blocking mode
        self.stdscr.timeout(0)


class Menu:
    def __init__(self, stdscr):
        try:
            print("Initializing menu...", file=sys.stderr)
            self.stdscr = stdscr
            # Reduce dimensions to avoid writing to the last cell
            self.height, self.width = stdscr.getmaxyx()
            print(f"Terminal size: {self.width}x{self.height}", file=sys.stderr)
            self.height -= 2
            self.width -= 2
            print(f"Menu area size: {self.width}x{self.height}", file=sys.stderr)
            self.running = True
            
            # Initialize core components with error handling
            try:
                self.scoreboard = ScoreBoard()
            except Exception as e:
                print(f"Error initializing scoreboard: {e}", file=sys.stderr)
                # Create a default scoreboard if initialization fails
                self.scoreboard = ScoreBoard("scoreboard.json.backup")
                
            try:
                self.settings = Settings()
            except Exception as e:
                print(f"Error initializing settings: {e}", file=sys.stderr)
                # Create default settings if initialization fails
                self.settings = Settings("settings.json.backup")
                
            self.current_menu = "main"
            self.selected_option = 0
            
            # Ensure clean input state for menu
            curses.flushinp()
            
            print("Menu initialized", file=sys.stderr)
        except Exception as e:
            print(f"Error in menu initialization: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            # Set minimal working state
            self.running = False

    def setup(self):
        print("Setting up menu...", file=sys.stderr)
        try:
            curses.curs_set(0)  # Hide cursor
            curses.noecho()
            curses.cbreak()
            self.stdscr.keypad(True)
            print("Menu setup complete", file=sys.stderr)
        except Exception as e:
            print(f"Error during menu setup: {e}", file=sys.stderr)
            raise
        
        # Set up colors if available
        if curses.has_colors():
            curses.start_color()
            # Basic UI colors
            curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)  # Normal text
            curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Selected text
            
            # Game element colors
            curses.init_pair(COLOR_PAIR_WHITE, curses.COLOR_WHITE, curses.COLOR_BLACK)
            curses.init_pair(COLOR_PAIR_RED, curses.COLOR_RED, curses.COLOR_BLACK)
            curses.init_pair(COLOR_PAIR_GREEN, curses.COLOR_GREEN, curses.COLOR_BLACK)
            curses.init_pair(COLOR_PAIR_YELLOW, curses.COLOR_YELLOW, curses.COLOR_BLACK)
            curses.init_pair(COLOR_PAIR_BLUE, curses.COLOR_BLUE, curses.COLOR_BLACK)

    def safe_addstr(self, y, x, text, attr=0):
        """Safe function to draw text with boundary checking"""
        try:
            # Skip if position is out of bounds
            if y < 0 or y >= self.height or x < 0:
                return
                
            # Handle bottom screen edge specially
            if y >= self.height - 1:
                # Don't write to last line if text would overflow
                if x + len(text) >= self.width - 1:
                    text = text[:self.width - x - 2]  # Leave two spaces at the end
            else:
                # For other lines, just truncate at screen width
                if x + len(text) >= self.width:
                    text = text[:self.width - x - 1]
                    
            if text:  # Only draw if there's text to draw
                self.stdscr.addstr(y, x, text, attr)
        except:
            pass  # Silently ignore curses errors

    def draw_menu(self):
        self.stdscr.clear()
        
        # Draw title
        title = "SPACE SHOOTER"
        self.safe_addstr(2, (self.width - len(title)) // 2, title, curses.A_BOLD)
        
        # Draw menu options based on current menu
        if self.current_menu == "main":
            options = ["New Game", "Score Board", "Settings", "Quit"]
        elif self.current_menu == "scoreboard":
            options = ["Back to Main Menu"]
        elif self.current_menu == "color_selection":
            options = list(PLAYER_COLORS.keys()) + ["Back to Settings"]
        elif self.current_menu == "difficulty_selection":
            options = list(DIFFICULTY_OPTIONS.keys()) + ["Back to Settings"]
        elif self.current_menu == "settings":
            options = ["Set Player Name", "Set Player Color", "Set Difficulty", "Clear Score Board", "Back to Main Menu"]
        else:
            options = ["Back to Main Menu"]
        
        # Keep the menu in the same upper-screen visual area as the compact
        # game grid instead of vertically centering it in the full terminal.
        # This prevents the menu from sitting far below the active game window
        # when the terminal is tall.
        menu_top_y = 6
        nav_y = min(GAME_GRID_HEIGHT + 2, self.height - 4)

        # Draw current difficulty above the navigation instructions.
        current_difficulty = self.settings.get_difficulty()
        difficulty_text = f"Current Difficulty: {current_difficulty}"
        self.safe_addstr(nav_y - 1, (self.width - len(difficulty_text)) // 2, difficulty_text)

        # Draw navigation help closer to the compact game area.
        nav_help = "[ Use ↑/↓ arrows to navigate. Enter to select ]"
        self.safe_addstr(nav_y, (self.width - len(nav_help)) // 2, nav_help)

        # Draw a visual window-height guide below the instructions.
        guide_text = " adjust game window bottom to this line "
        guide_width = min(self.width - 4, 72)
        side_width = max(0, (guide_width - len(guide_text)) // 2)
        guide_line = "─" * side_width + guide_text + "─" * max(0, guide_width - side_width - len(guide_text))
        self.safe_addstr(nav_y + 1, (self.width - len(guide_line)) // 2, guide_line)

        # Draw options in a fixed upper layout that matches the smaller
        # game window instead of using self.height // 2.
        for i, option in enumerate(options):
            y = menu_top_y + i
            x = (self.width - len(option)) // 2
            
            # Add selection indicator
            if i == self.selected_option:
                option_text = f"➤ {option} ←"
                self.safe_addstr(y, x - 3, option_text, curses.A_BOLD | curses.A_REVERSE)
            else:
                option_text = f"  {option}  "
                self.safe_addstr(y, x - 3, option_text)
        
        # Draw scoreboard if in scoreboard menu
        if self.current_menu == "scoreboard":
            scores = self.scoreboard.get_scores()
            if scores:
                # Fixed column widths with proper spacing - adjusted for better layout
                start_x = 4
                rank_width = 5  # Reduced from 6
                name_width = 15  # Reduced from 20
                score_width = 10  # Reduced from 12
                date_width = 16  # Reduced from 20
                col_padding = 3  # Increased from 2 for better separation
                
                # Calculate total width needed
                total_width = rank_width + name_width + score_width + date_width + (col_padding * 3)
                
                # Center the table
                start_x = max(4, (self.width - total_width) // 2)
                
                # Draw headers with proper spacing
                self.safe_addstr(6, start_x, "Rank".ljust(rank_width), curses.A_BOLD)
                self.safe_addstr(6, start_x + rank_width + col_padding, "Name".ljust(name_width), curses.A_BOLD)
                self.safe_addstr(6, start_x + rank_width + name_width + col_padding * 2, "Score".ljust(score_width), curses.A_BOLD)
                self.safe_addstr(6, start_x + rank_width + name_width + score_width + col_padding * 3, "Date".ljust(date_width), curses.A_BOLD)
                
                # Draw separator line with proper length
                separator = "─" * total_width
                self.safe_addstr(7, start_x, separator)
                
                # Draw scores with proper truncation and spacing
                for i, score in enumerate(scores[:10]):
                    y = 8 + i
                    
                    # Format each field
                    rank_text = f"{i+1}.".ljust(rank_width)
                    name_text = (score["name"][:name_width-3] + "...") if len(score["name"]) > name_width else score["name"].ljust(name_width)
                    score_text = str(score["score"]).rjust(score_width)  # Right-align scores
                    date_text = score["date"][:date_width].ljust(date_width)
                    
                    # Draw each field with proper spacing
                    self.safe_addstr(y, start_x, rank_text)
                    self.safe_addstr(y, start_x + rank_width + col_padding, name_text)
                    self.safe_addstr(y, start_x + rank_width + name_width + col_padding * 2, score_text)
                    self.safe_addstr(y, start_x + rank_width + name_width + score_width + col_padding * 3, date_text)
            else:
                msg = "No scores yet!"
                self.safe_addstr(8, (self.width - len(msg)) // 2, msg)

    def handle_input(self):
        try:
            # Clear any stale input first
            if self.current_menu == "main":
                # Only clear input when entering main menu to avoid losing inputs
                curses.flushinp()
                
            key = self.stdscr.getch()
            print(f"Menu received key: {key}", file=sys.stderr)
            
            # Navigate menu
            if key == curses.KEY_UP and self.selected_option > 0:
                self.selected_option -= 1
            elif key == curses.KEY_DOWN:
                if self.current_menu == "main" and self.selected_option < 3:
                    self.selected_option += 1
                elif self.current_menu == "scoreboard" and self.selected_option < 0:
                    self.selected_option += 1
                elif self.current_menu == "settings" and self.selected_option < 4:
                    self.selected_option += 1
                elif self.current_menu == "color_selection" and self.selected_option < len(PLAYER_COLORS.keys()):
                    self.selected_option += 1
                elif self.current_menu == "difficulty_selection" and self.selected_option < len(DIFFICULTY_OPTIONS.keys()):
                    self.selected_option += 1
            elif key == 10 or key == 13:  # Enter key (10 is LF, 13 is CR)
                self.select_option()
            elif key == 27:  # Escape key
                if self.current_menu != "main":
                    self.current_menu = "main"
                    self.selected_option = 0
                    print("Returned to main menu using ESC key", file=sys.stderr)
        except Exception as e:
            print(f"Error in handle_input: {e}", file=sys.stderr)

    def select_option(self):
        try:
            if self.current_menu == "main":
                if self.selected_option == 0:  # New Game
                    print("Starting new game...", file=sys.stderr)
                    game = Game(self.stdscr)
                    game.run_game()
                    # Reset terminal state after game ends
                    curses.flushinp()  # Clear pending input
                    self.stdscr.timeout(-1)  # Reset to blocking mode
                    self.stdscr.clear()  # Clear screen
                    self.stdscr.refresh()
                    
                    # Add a small delay to ensure terminal stability
                    curses.napms(100)
                    
                    print("Game ended, back to menu", file=sys.stderr)
                elif self.selected_option == 1:  # Score Board
                    self.current_menu = "scoreboard"
                    self.selected_option = 0
                elif self.selected_option == 2:  # Settings
                    self.current_menu = "settings"
                    self.selected_option = 0
                elif self.selected_option == 3:  # Quit
                    self.running = False
            elif self.current_menu == "scoreboard":
                # Back to main menu
                self.current_menu = "main"
                self.selected_option = 0
            elif self.current_menu == "settings":
                if self.selected_option == 0:  # Set Player Name
                    self.get_player_name()
                elif self.selected_option == 1:  # Set Player Color
                    self.current_menu = "color_selection"
                    self.selected_option = 0
                elif self.selected_option == 2:  # Set Difficulty
                    self.current_menu = "difficulty_selection"
                    # Highlight current difficulty setting
                    current_difficulty = self.settings.get_difficulty()
                    print(f"Current difficulty setting: {current_difficulty}", file=sys.stderr)
                    if current_difficulty in DIFFICULTY_OPTIONS:
                        self.selected_option = list(DIFFICULTY_OPTIONS.keys()).index(current_difficulty)
                    else:
                        self.selected_option = 1  # Default to Medium
                elif self.selected_option == 3:  # Clear Score Board
                    self.scoreboard.clear_scores()
                    # Show confirmation message
                    self.safe_addstr(self.height - 3, (self.width - len("Scoreboard cleared!")) // 2, "Scoreboard cleared!")
                    self.stdscr.refresh()
                    curses.napms(1500)  # Show message for 1.5 seconds
                elif self.selected_option == 4:  # Back to Main Menu
                    self.current_menu = "main"
                    self.selected_option = 0
            elif self.current_menu == "color_selection":
                color_options = list(PLAYER_COLORS.keys())
                back_option_index = len(color_options)
                
                if self.selected_option < back_option_index:
                    # Set player color
                    selected_color = color_options[self.selected_option]
                    self.settings.set_player_color(selected_color)
                    
                    # Show confirmation message
                    msg = f"Player color set to: {selected_color}"
                    self.safe_addstr(self.height - 3, (self.width - len(msg)) // 2, msg)
                    self.stdscr.refresh()
                    curses.napms(1500)  # Show message for 1.5 seconds
                    
                    # Return to settings menu
                    self.current_menu = "settings"
                    self.selected_option = 1  # Highlight Color option
                else:
                    # Back to settings
                    self.current_menu = "settings"
                    self.selected_option = 1  # Highlight Color option
            elif self.current_menu == "difficulty_selection":
                difficulty_options = list(DIFFICULTY_OPTIONS.keys())
                back_option_index = len(difficulty_options)
                
                if self.selected_option < back_option_index:
                    # Set difficulty
                    selected_difficulty = difficulty_options[self.selected_option]
                    self.settings.set_difficulty(selected_difficulty)
                    fps = DIFFICULTY_OPTIONS[selected_difficulty]
                    print(f"Set difficulty to: {selected_difficulty} ({fps} FPS)", file=sys.stderr)
                    
                    # Show confirmation message
                    msg = f"Difficulty set to: {selected_difficulty} ({fps} FPS)"
                    effect_msg = "Changes will apply in the next game"
                    self.safe_addstr(self.height - 4, (self.width - len(msg)) // 2, msg)
                    self.safe_addstr(self.height - 3, (self.width - len(effect_msg)) // 2, effect_msg)
                    self.stdscr.refresh()
                    curses.napms(1500)  # Show message for 1.5 seconds
                    
                    # Return to settings menu
                    self.current_menu = "settings"
                    self.selected_option = 2  # Highlight Difficulty option
                else:
                    # Back to settings
                    self.current_menu = "settings"
                    self.selected_option = 2  # Highlight Difficulty option
        except Exception as e:
            print(f"Error in select_option: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    def get_player_name(self):
        prompt = "Enter your name: "
        input_width = 20
        prompt_x = max(0, (self.width - len(prompt) - input_width) // 2)
        y = self.height - 4  # Move up to avoid overlay
        validation_y = y + 1

        # Clear input areas
        self.stdscr.move(y, 0)
        self.stdscr.clrtoeol()
        self.stdscr.move(validation_y, 0)
        self.stdscr.clrtoeol()
        
        self.safe_addstr(y, prompt_x, prompt)
        self.stdscr.refresh()
        
        curses.curs_set(1)  # Show cursor
        name = ""
        max_name_length = 15
        x = prompt_x + len(prompt)
        
        # Ensure we don't exceed screen boundaries
        if x + input_width >= self.width:
            input_width = self.width - x - 1
        
        while True:
            try:
                # Clear input area and validation message
                self.safe_addstr(y, x, " " * input_width)
                self.safe_addstr(validation_y, 0, " " * self.width)
                
                # Show current name
                self.safe_addstr(y, x, name)
                
                # Show validation message if empty
                if not name.strip():
                    msg = "Name cannot be empty. Press Enter to confirm or Escape to cancel."
                    self.safe_addstr(validation_y, (self.width - len(msg)) // 2, msg)
                
                # Position cursor
                self.stdscr.move(y, x + len(name))
                self.stdscr.refresh()
                
                key = self.stdscr.getch()
                
                if key == 10 or key == 13:  # Enter
                    if name.strip():  # Only accept non-empty names
                        break
                    else:
                        msg = "Please enter a valid name!"
                        self.safe_addstr(validation_y, (self.width - len(msg)) // 2, msg, curses.A_BOLD)
                        curses.flash()
                elif key == 27:  # Escape
                    name = ""
                    break
                elif key in (8, 127, curses.KEY_BACKSPACE):  # Handle all backspace keys
                    if name:
                        name = name[:-1]
                elif 32 <= key <= 126 and len(name) < max_name_length:  # Printable ASCII
                    if len(name.strip()) < max_name_length:  # Check length after stripping
                        name += chr(key)
                    else:
                        curses.flash()  # Visual feedback for max length
                    
            except Exception as e:
                print(f"Error in name input: {e}", file=sys.stderr)
                continue

        # Clean up
        self.stdscr.move(y, 0)
        self.stdscr.clrtoeol()
        self.stdscr.move(validation_y, 0)
        self.stdscr.clrtoeol()
        curses.curs_set(0)  # Hide cursor

        # Save the name if entered
        if name:
            name = name.strip()
            if name:  # Double check it's not empty after strip
                self.settings.set_player_name(name)
                # Show confirmation
                msg = f"Name set to: {name}"
                self.safe_addstr(y, (self.width - len(msg)) // 2, msg)
                self.stdscr.refresh()
                curses.napms(1500)

        # Return to settings menu
        self.current_menu = "settings"
        self.selected_option = 0

    def run(self):
        try:
            # Menu setup
            self.setup()
            self.stdscr.timeout(-1)  # Wait for user input
            
            print("Entering menu loop", file=sys.stderr)
            # Menu loop
            while self.running:
                try:
                    # Draw menu
                    self.draw_menu()
                    
                    # Handle input
                    self.handle_input()
                    
                    # Refresh screen
                    self.stdscr.refresh()
                    
                    # Add a small delay to prevent high CPU usage (60 FPS = ~16.7ms)
                    curses.napms(16)
                except Exception as e:
                    print(f"Error in menu loop: {e}", file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)
                    
                    # Try to recover from error
                    try:
                        self.stdscr.clear()
                        self.stdscr.refresh()
                        curses.flushinp()
                        
                        # Display error message
                        error_msg = f"Error: {str(e)}"
                        self.safe_addstr(self.height//2, (self.width - len(error_msg))//2, error_msg, curses.A_BOLD)
                        continue_msg = "Press any key to continue..."
                        self.safe_addstr(self.height//2 + 1, (self.width - len(continue_msg))//2, continue_msg)
                        self.stdscr.refresh()
                        
                        # Wait for user input
                        self.stdscr.timeout(-1)
                        self.stdscr.getch()
                        self.stdscr.timeout(0)
                        
                        # Continue running if possible
                        continue
                    except:
                        # If recovery fails, exit menu
                        self.running = False
            print("Exiting menu loop", file=sys.stderr)
        except Exception as e:
            print(f"Fatal error in menu run: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)


def check_terminal_size(stdscr):
    """Check if terminal is large enough for the game"""
    height, width = stdscr.getmaxyx()
    min_height = 20
    min_width = 60
    
    if height < min_height or width < min_width:
        stdscr.clear()
        message = f"Terminal too small: {width}x{height}. Minimum required: {min_width}x{min_height}"
        if height > 3 and width > len(message) + 4:
            stdscr.addstr(height//2, max(0, (width - len(message))//2), message)
            stdscr.addstr(height//2 + 1, max(0, (width - 25)//2), "Press any key to exit...")
            stdscr.refresh()
            stdscr.getch()
        print(f"Error: {message}", file=sys.stderr)
        return False
    return True

def main(stdscr):
    try:
        print("Starting space shooter game...", file=sys.stderr)
        
        # Clear screen
        stdscr.clear()
        
        # Reset any terminal state that might be corrupted
        curses.flushinp()
                
        print("Terminal size check passed", file=sys.stderr)
        
        # Create and run menu with robust error handling
        try:
            # First reset terminal state completely
            stdscr.keypad(True)
            curses.noecho()
            curses.cbreak()
            
            # Clear any pending input
            curses.flushinp()
            stdscr.clear()
            stdscr.refresh()
            
            # Create and run menu
            menu = Menu(stdscr)
            menu.run()
        except Exception as e:
            print(f"Error in menu: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            stdscr.clear()
            error_msg = f"Error: {str(e)}"
            stdscr.addstr(0, 0, error_msg[:stdscr.getmaxyx()[1]-1])
            stdscr.addstr(1, 0, "Press any key to exit...")
            stdscr.refresh()
            stdscr.getch()
    except Exception as e:
        print(f"Fatal error in main: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)


if __name__ == "__main__":
    # Initialize curses
    print("Initializing game...", file=sys.stderr)
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        print("Game interrupted by user", file=sys.stderr)
    except Exception as e:
        print(f"Unhandled error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    finally:
        # Ensure terminal is reset properly
        print("Cleaning up and exiting...", file=sys.stderr)
        try:
            curses.endwin()
        except:
            pass
        print("Game exited", file=sys.stderr)
