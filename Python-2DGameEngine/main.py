import pygame
import sys
from player import Player

# Initialize pygame
pygame.init()

# Display
WIDTH, HEIGHT = 500, 400
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Simple Pygame Engine")

# Colors
WHITE = (255, 255, 255)

# Entities
player = Player(
    x=WIDTH // 2 - 15,
    y=HEIGHT // 2 - 15,
)

# Main loop
clock = pygame.time.Clock()
running = True

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    keys = pygame.key.get_pressed()
    player.handle_input(keys, WIDTH, HEIGHT)

    screen.fill(WHITE)
    player.draw(screen)

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
sys.exit()
