import pygame


class Player:
    def __init__(self, x: int, y: int, size: int = 30, speed: int = 5):
        self.x = x
        self.y = y
        self.size = size
        self.speed = speed
        self.color = (30, 144, 255)  # BLUE

    def handle_input(self, keys, screen_width: int, screen_height: int):
        if keys[pygame.K_LEFT] and self.x > 0:
            self.x -= self.speed
        if keys[pygame.K_RIGHT] and self.x < screen_width - self.size:
            self.x += self.speed
        if keys[pygame.K_UP] and self.y > 0:
            self.y -= self.speed
        if keys[pygame.K_DOWN] and self.y < screen_height - self.size:
            self.y += self.speed

    def draw(self, screen):
        pygame.draw.rect(screen, self.color, (self.x, self.y, self.size, self.size))
