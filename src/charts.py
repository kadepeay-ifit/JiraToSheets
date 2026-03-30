from pathlib import Path
import matplotlib.pyplot as plt
from datetime import datetime



# Create and save a pie chart based off of the stability of the sheet
def make_pie_chart(status_counts, BUILD):
     """
     Create and save a pie chart visualization of status counts.
     Args:
          status_counts (dict): A dictionary with status names as keys and their counts as values.
     Returns:
          pathlib.Path | None: Path to the saved chart image if created, else None.
     Description:
          Filters out statuses with zero counts, creates a pie chart with the remaining statuses,
          and saves it as an image file with a timestamp. The chart includes percentage labels
          and is rotated for better readability. Each status is mapped to a specific color.
     Side Effects:
          - Displays a pie chart using matplotlib
          - Saves the figure to the 'images/' directory with format: {BUILD}_{timestamp}.png
          - Prints a message confirming the file save location
     """

     # Map statuses to their corresponding colors
     color_mapping = {
          'passed': 'springgreen',
          'failed': 'indianred',
          'untestable': 'skyblue',
          'in progress': 'yellow',
          'monitoring': 'mediumorchid',
          'blocked': 'orange',
          '': 'gray' # Just in case there is any blank values
     }
     
     filtered_counts = {}
     colors = []
     for key, val in status_counts.items():
          if val > 0:
               filtered_counts[key] = val
               colors.append(color_mapping.get(key, "gray"))

     if not filtered_counts:
          print("No status counts available to chart.")
          return None

     plt.figure(figsize=(8, 8))
     
     plt.pie(filtered_counts.values(), labels=filtered_counts.keys(), autopct='%1.1f%%', startangle=45, rotatelabels=True, colors=colors) 
     plt.title(f"Current Health of {BUILD}")

     # Save the pie chart with datetime in ISO format
     current_datetime = datetime.now()
     formatted_datetime = current_datetime.strftime("%Y-%m-%d_%H-%M-%S")
     fig_name = f"{BUILD}_PI_{formatted_datetime}.png"
     output_dir = Path("images")
     output_dir.mkdir(parents=True, exist_ok=True)
     output_path = output_dir / fig_name
     plt.savefig(output_path)
     plt.close()

     # print(f"Saved pie chart: {output_path}")
     return output_path


def make_bar_graph(priority_counts, BUILD):
     
     # Map priorities to a corresponding color
     color_mapping = {
          'lowest': 'skyblue',
          'low': 'lightblue',
          'medium': 'yellow',
          'high': 'orange',
          'highest': 'red',
     }

     filtered_counts = {}
     colors = []
     for key, val in priority_counts.items():
          if val > 0:
               filtered_counts[key] = val
               colors.append(color_mapping.get(key, "gray"))

     if not filtered_counts:
          print("No priority counts available to graph.")
          return None
     
     plt.figure(figsize=(8, 8))

     plt.bar(filtered_counts.keys(), filtered_counts.values(), color=colors)
     plt.title(f"Priority Health of {BUILD}")

     # Save the bar graph with datetime in ISO format
     current_datetime = datetime.now()
     formatted_datetime = current_datetime.strftime("%Y-%m-%d_%H-%M-%S")
     fig_name = f"{BUILD}_BAR_{formatted_datetime}.png"
     output_dir = Path("images")
     output_dir.mkdir(parents=True, exist_ok=True)
     output_path = output_dir / fig_name
     plt.savefig(output_path)
     plt.close()

     # print(f"Saved bar chart: {output_path}")
     return output_path